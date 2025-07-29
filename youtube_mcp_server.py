#!/usr/bin/env python3

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# YouTube API configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

class YouTubeClient:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.youtube = None
    
    def authenticate(self):
        """Authenticate with YouTube API using OAuth2"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise Exception(f"Error: {self.credentials_file} not found! Please download OAuth2 credentials from Google Cloud Console")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.youtube = build(API_SERVICE_NAME, API_VERSION, credentials=creds)
        return self.youtube
    
    def get_subscribed_channels(self) -> List[Dict[str, str]]:
        """Get all channels the user is subscribed to"""
        if not self.youtube:
            self.authenticate()
            
        channels = []
        next_page_token = None
        
        while True:
            request = self.youtube.subscriptions().list(
                part='snippet',
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                channel_info = {
                    'channel_id': item['snippet']['resourceId']['channelId'],
                    'channel_title': item['snippet']['title'],
                    'description': item['snippet']['description']
                }
                channels.append(channel_info)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        
        return channels
    
    def get_channel_latest_videos(self, channel_id: str, hours_ago: int = 24) -> List[Dict[str, Any]]:
        """Get latest videos from a specific channel within the last X hours"""
        if not self.youtube:
            self.authenticate()
            
        # Calculate time threshold
        time_threshold = datetime.utcnow() - timedelta(hours=hours_ago)
        
        try:
            # Get channel's uploads playlist
            channel_request = self.youtube.channels().list(
                part='contentDetails',
                id=channel_id
            )
            channel_response = channel_request.execute()
            
            if not channel_response['items']:
                return []
            
            uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get recent videos from uploads playlist
            playlist_request = self.youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=10
            )
            playlist_response = playlist_request.execute()
            
            recent_videos = []
            for item in playlist_response['items']:
                published_at = datetime.strptime(
                    item['snippet']['publishedAt'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                )
                
                # Only include videos published within the time threshold
                if published_at >= time_threshold:
                    video_info = {
                        'video_id': item['snippet']['resourceId']['videoId'],
                        'title': item['snippet']['title'],
                        'published_at': item['snippet']['publishedAt'],
                        'description': item['snippet']['description'][:200] + '...' if len(item['snippet']['description']) > 200 else item['snippet']['description'],
                        'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                        'url': f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}"
                    }
                    recent_videos.append(video_info)
            
            return recent_videos
            
        except Exception as e:
            raise Exception(f"Error getting videos for channel {channel_id}: {str(e)}")
    
    def get_all_latest_videos(self, hours_ago: int = 24) -> List[Dict[str, Any]]:
        """Get latest videos from all subscribed channels"""
        channels = self.get_subscribed_channels()
        
        all_recent_videos = []
        
        for channel in channels:
            recent_videos = self.get_channel_latest_videos(
                channel['channel_id'], 
                hours_ago
            )
            
            for video in recent_videos:
                video['channel_title'] = channel['channel_title']
                all_recent_videos.append(video)
        
        # Sort by published date (newest first)
        all_recent_videos.sort(
            key=lambda x: datetime.strptime(x['published_at'], '%Y-%m-%dT%H:%M:%SZ'),
            reverse=True
        )
        
        return all_recent_videos

# Initialize YouTube client
youtube_client = YouTubeClient()

# Create FastMCP app
mcp = FastMCP("YouTube Latest Videos",request_timeout=300) # 5 minutes

@mcp.tool()
def get_latest_youtube_videos(hours_ago: int = 24, limit: int = 50) -> str:
    """Get the latest videos from all YouTube channels you're subscribed to.
    
    Args:
        hours_ago: Number of hours to look back for new videos (default: 24)
        limit: Maximum number of videos to return (default: 50)
    """
    try:
        videos = youtube_client.get_all_latest_videos(hours_ago)
        
        # Apply limit
        if limit and len(videos) > limit:
            videos = videos[:limit]
        
        if not videos:
            return f"No new videos found in the last {hours_ago} hours from your subscribed channels."
        
        # Format the response
        result = {
            "total_videos": len(videos),
            "hours_checked": hours_ago,
            "videos": videos
        }
        
        response_text = f"Found {len(videos)} new videos in the last {hours_ago} hours:\n\n"
        
        for video in videos:
            published_utc = datetime.strptime(video['published_at'], '%Y-%m-%dT%H:%M:%SZ')
            published_local = published_utc.strftime('%Y-%m-%d %H:%M UTC')
            
            response_text += f"📺 **{video['channel_title']}**\n"
            response_text += f"🎬 {video['title']}\n"
            response_text += f"🕒 {published_local}\n"
            response_text += f"🔗 {video['url']}\n"
            if video['description']:
                response_text += f"📝 {video['description']}\n"
            response_text += "\n" + "-" * 50 + "\n\n"
        
        response_text += f"\nJSON Data:\n```json\n{json.dumps(result, indent=2)}\n```"
        return response_text
        
    except Exception as e:
        return f"Error getting latest YouTube videos: {str(e)}"

@mcp.tool()
def get_subscribed_channels() -> str:
    """Get a list of all YouTube channels you're subscribed to."""
    try:
        channels = youtube_client.get_subscribed_channels()
        
        response_text = f"You are subscribed to {len(channels)} channels:\n\n"
        
        for channel in channels:
            response_text += f"📺 **{channel['channel_title']}**\n"
            response_text += f"🆔 {channel['channel_id']}\n"
            if channel['description']:
                desc = channel['description'][:100] + '...' if len(channel['description']) > 100 else channel['description']
                response_text += f"📝 {desc}\n"
            response_text += "\n"
        
        response_text += f"\nJSON Data:\n```json\n{json.dumps(channels, indent=2)}\n```"
        return response_text
        
    except Exception as e:
        return f"Error getting subscribed channels: {str(e)}"

@mcp.tool()
def get_channel_videos(channel_id: str, hours_ago: int = 24) -> str:
    """Get latest videos from a specific YouTube channel.
    
    Args:
        channel_id: The YouTube channel ID
        hours_ago: Number of hours to look back for new videos (default: 24)
    """
    try:
        videos = youtube_client.get_channel_latest_videos(channel_id, hours_ago)
        
        if not videos:
            return f"No new videos found in the last {hours_ago} hours for channel {channel_id}."
        
        response_text = f"Found {len(videos)} new videos in the last {hours_ago} hours:\n\n"
        
        for video in videos:
            published_utc = datetime.strptime(video['published_at'], '%Y-%m-%dT%H:%M:%SZ')
            published_local = published_utc.strftime('%Y-%m-%d %H:%M UTC')
            
            response_text += f"🎬 {video['title']}\n"
            response_text += f"🕒 {published_local}\n"
            response_text += f"🔗 {video['url']}\n"
            if video['description']:
                response_text += f"📝 {video['description']}\n"
            response_text += "\n" + "-" * 50 + "\n\n"
        
        response_text += f"\nJSON Data:\n```json\n{json.dumps(videos, indent=2)}\n```"
        return response_text
        
    except Exception as e:
        return f"Error getting channel videos: {str(e)}"

if __name__ == "__main__":
    mcp.run()
