#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     "slack-sdk>=3.19.0",
#     "python-dotenv>=1.0.0"
# ]
# ///

"""
Slack Thread to Markdown Exporter

This script exports a Slack thread to a markdown file, including all messages,
usernames, timestamps, and thread structure.

SETUP:
------
1. Create a Slack App:
   - Go to https://api.slack.com/apps
   - Click "Create New App" -> "From scratch"
   - Name your app and select your workspace

2. Add OAuth Scopes:
   - Go to "OAuth & Permissions" in the sidebar
   - Under "Bot Token Scopes", add these scopes:
     * channels:history (for public channels)
     * groups:history (for private channels)
     * users:read (to fetch user information)
     * channels:read (to get channel info)
     * groups:read (for private channel info)

3. Install App to Workspace:
   - Click "Install to Workspace" button
   - Authorize the app
   - Copy the "Bot User OAuth Token" (starts with xoxb-)

4. Set up Authentication:
   Create a .env file in the same directory as this script:

   SLACK_BOT_TOKEN=xoxb-your-token-here

   OR set the environment variable:
   export SLACK_BOT_TOKEN=xoxb-your-token-here

USAGE:
------
./export_thread.py "https://your-workspace.slack.com/archives/C01234567/p1234567890123456"

The script will create a markdown file named: thread_CHANNEL_TIMESTAMP.md
"""

import os
import sys
import re
from datetime import datetime
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def parse_slack_url(url):
    """
    Parse a Slack thread URL to extract channel ID and thread timestamp.

    Supports formats:
    - https://workspace.slack.com/archives/C01234567/p1234567890123456
    - https://workspace.slack.com/archives/C01234567/p1234567890123456?thread_ts=1234567890.123456
    """
    pattern = r'slack\.com/archives/([A-Z0-9]+)/p(\d+)'
    match = re.search(pattern, url)

    if not match:
        raise ValueError(f"Invalid Slack URL format: {url}")

    channel_id = match.group(1)
    # Convert timestamp: p1234567890123456 -> 1234567890.123456
    ts_raw = match.group(2)
    timestamp = f"{ts_raw[:-6]}.{ts_raw[-6:]}"

    return channel_id, timestamp


def get_user_name(client, user_id, user_cache):
    """Get user's display name or real name from Slack API."""
    if user_id in user_cache:
        return user_cache[user_id]

    try:
        result = client.users_info(user=user_id)
        user = result["user"]
        # Prefer display name, fall back to real name
        name = user["profile"].get("display_name") or user["profile"].get("real_name") or user["name"]
        user_cache[user_id] = name
        return name
    except SlackApiError as e:
        print(f"Warning: Could not fetch user {user_id}: {e.response['error']}", file=sys.stderr)
        user_cache[user_id] = user_id
        return user_id


def format_timestamp(ts):
    """Convert Slack timestamp to readable format."""
    timestamp = float(ts)
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_message(msg, client, user_cache, indent_level=0):
    """Format a single message as markdown."""
    indent = "  " * indent_level
    user_id = msg.get("user", "Unknown")
    user_name = get_user_name(client, user_id, user_cache)
    text = msg.get("text", "")
    ts = msg.get("ts", "")
    timestamp = format_timestamp(ts)

    # Basic formatting
    lines = []
    lines.append(f"{indent}**{user_name}** - *{timestamp}*")
    lines.append(f"{indent}{text}")
    lines.append("")

    return "\n".join(lines)


def export_thread(url, output_file=None):
    """Export a Slack thread to markdown."""
    # Get token from environment
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        print("Error: SLACK_BOT_TOKEN not found in environment variables.", file=sys.stderr)
        print("Please set it in a .env file or as an environment variable.", file=sys.stderr)
        print("See script documentation for setup instructions.", file=sys.stderr)
        sys.exit(1)

    client = WebClient(token=token)

    # Parse URL
    try:
        channel_id, thread_ts = parse_slack_url(url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Cache for user information
    user_cache = {}

    try:
        # Get channel info
        try:
            channel_info = client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"]
        except SlackApiError:
            channel_name = channel_id

        # Fetch the parent message
        result = client.conversations_history(
            channel=channel_id,
            latest=thread_ts,
            inclusive=True,
            limit=1
        )

        if not result["messages"]:
            print(f"Error: Could not find message with timestamp {thread_ts}", file=sys.stderr)
            sys.exit(1)

        parent_msg = result["messages"][0]

        # Fetch all replies in the thread
        replies = []
        if parent_msg.get("reply_count", 0) > 0:
            replies_result = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            # Skip the first message as it's the parent
            replies = replies_result["messages"][1:]

        # Generate output filename if not provided
        if output_file is None:
            safe_channel = re.sub(r'[^\w\-]', '_', channel_name)
            safe_ts = thread_ts.replace('.', '_')
            output_file = f"thread_{safe_channel}_{safe_ts}.md"

        # Build markdown content
        markdown_lines = []
        markdown_lines.append(f"# Slack Thread Export")
        markdown_lines.append(f"")
        markdown_lines.append(f"**Channel:** #{channel_name}")
        markdown_lines.append(f"**Thread URL:** {url}")
        markdown_lines.append(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        markdown_lines.append(f"")
        markdown_lines.append(f"---")
        markdown_lines.append(f"")
        markdown_lines.append(f"## Thread")
        markdown_lines.append(f"")

        # Add parent message
        markdown_lines.append(format_message(parent_msg, client, user_cache))

        # Add replies
        if replies:
            markdown_lines.append(f"### Replies ({len(replies)})")
            markdown_lines.append(f"")
            for reply in replies:
                markdown_lines.append(format_message(reply, client, user_cache, indent_level=1))

        # Write to file
        markdown_content = "\n".join(markdown_lines)
        Path(output_file).write_text(markdown_content, encoding="utf-8")

        print(f"✓ Thread exported successfully to: {output_file}")
        print(f"  Messages: {1 + len(replies)}")

    except SlackApiError as e:
        error = e.response["error"]
        print(f"Error: Slack API error: {error}", file=sys.stderr)

        if error == "invalid_auth":
            print("Your Slack token is invalid. Please check your SLACK_BOT_TOKEN.", file=sys.stderr)
        elif error == "missing_scope":
            print("Your Slack app is missing required permissions.", file=sys.stderr)
            print("Please add the required scopes (see script documentation).", file=sys.stderr)
        elif error == "channel_not_found":
            print("Channel not found. Make sure your bot is added to the channel.", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./export_thread.py <slack_thread_url> [output_file.md]", file=sys.stderr)
        print("", file=sys.stderr)
        print("Example:", file=sys.stderr)
        print('  ./export_thread.py "https://workspace.slack.com/archives/C01234567/p1234567890123456"', file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    export_thread(url, output_file)
