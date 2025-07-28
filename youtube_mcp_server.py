#!/usr/bin/env python3

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Sequence

from mcp import ClientSession, StdioServerSession
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

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
    
    async def authenticate(self):
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
    
    async def get_subscribed_channels(self):
        """Get all channels the user is subscribed to"""
        if not self.youtube:
            await self.authenticate()
            
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
    
    async def get_channel_latest_videos(self, channel_id, hours_ago=24):
        """Get latest videos from a specific channel within the last X hours"""
        if not self.youtube:
            await self.authenticate()
            
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
    
    async def get_all_latest_videos(self, hours_ago=24):
        """Get latest videos from all subscribed channels"""
        channels = await self.get_subscribed_channels()
        
        all_recent_videos = []
        
        for channel in channels:
            recent_videos = await self.get_channel_latest_videos(
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

# Create MCP server
server = Server("youtube-latest-videos")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="get_latest_youtube_videos",
            description="Get the latest videos from all YouTube channels you're subscribed to",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_ago": {
                        "type": "number",
                        "description": "Number of hours to look back for new videos (default: 24)",
                        "default": 24
                    },
                    "limit": {
                        "type": "number",  
                        "description": "Maximum number of videos to return (default: 50)",
                        "default": 50
                    }
                }
            }
        ),
        types.Tool(
            name="get_subscribed_channels",
            description="Get a list of all YouTube channels you're subscribed to",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="get_channel_videos",
            description="Get latest videos from a specific YouTube channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The YouTube channel ID"
                    },
                    "hours_ago": {
                        "type": "number",
                        "description": "Number of hours to look back for new videos (default: 24)",
                        "default": 24
                    }
                },
                "required": ["channel_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "get_latest_youtube_videos":
        try:
            hours_ago = arguments.get("hours_ago", 24) if arguments else 24
            limit = arguments.get("limit", 50) if arguments else 50
            
            videos = await youtube_client.get_all_latest_videos(hours_ago)
            
            # Apply limit
            if limit and len(videos) > limit:
                videos = videos[:limit]
            
            if not videos:
                return [types.TextContent(
                    type="text",
                    text=f"No new videos found in the last {hours_ago} hours from your subscribed channels."
                )]
            
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
            
            return [
                types.TextContent(type="text", text=response_text),
                types.TextContent(type="text", text=f"JSON Data:\n```json\n{json.dumps(result, indent=2)}\n```")
            ]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error getting latest YouTube videos: {str(e)}"
            )]
    
    elif name == "get_subscribed_channels":
        try:
            channels = await youtube_client.get_subscribed_channels()
            
            response_text = f"You are subscribed to {len(channels)} channels:\n\n"
            
            for channel in channels:
                response_text += f"📺 **{channel['channel_title']}**\n"
                response_text += f"🆔 {channel['channel_id']}\n"
                if channel['description']:
                    desc = channel['description'][:100] + '...' if len(channel['description']) > 100 else channel['description']
                    response_text += f"📝 {desc}\n"
                response_text += "\n"
            
            return [
                types.TextContent(type="text", text=response_text),
                types.TextContent(type="text", text=f"JSON Data:\n```json\n{json.dumps(channels, indent=2)}\n```")
            ]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error getting subscribed channels: {str(e)}"
            )]
    
    elif name == "get_channel_videos":
        try:
            if not arguments or "channel_id" not in arguments:
                return [types.TextContent(
                    type="text",
                    text="Error: channel_id is required"
                )]
            
            channel_id = arguments["channel_id"]
            hours_ago = arguments.get("hours_ago", 24)
            
            videos = await youtube_client.get_channel_latest_videos(channel_id, hours_ago)
            
            if not videos:
                return [types.TextContent(
                    type="text",
                    text=f"No new videos found in the last {hours_ago} hours for channel {channel_id}."
                )]
            
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
            
            return [
                types.TextContent(type="text", text=response_text),
                types.TextContent(type="text", text=f"JSON Data:\n```json\n{json.dumps(videos, indent=2)}\n```")
            ]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error getting channel videos: {str(e)}"
            )]
    
    else:
        return [types.TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="youtube-latest-videos",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
