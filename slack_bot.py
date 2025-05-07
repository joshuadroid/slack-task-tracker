import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize the Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# In-memory task storage
# Format: {user_id: {task_id: {"text": task_text, "shared_with": [user_ids]}}}
tasks = defaultdict(dict)
task_counter = 0

def get_user_info(user_id):
    try:
        result = app.client.users_info(user=user_id)
        if result["ok"]:
            user = result["user"]
            return f"{user['name']} ({user_id})"
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
    return user_id

def get_channel_info(channel_id):
    try:
        # Check if it's a DM (starts with 'D')
        if channel_id.startswith('D'):
            try:
                # For DMs, we need to get the conversation info
                result = app.client.conversations_info(channel=channel_id)
                if result["ok"]:
                    # Get the other user in the DM
                    other_user_id = [user for user in result["channel"]["members"] if user != app.client.auth_test()["user_id"]][0]
                    other_user_info = get_user_info(other_user_id)
                    return f"DM with {other_user_info} ({channel_id})"
            except Exception as e:
                logger.error(f"Error fetching DM info: {e}")
                return f"DM ({channel_id})"
        else:
            # For regular channels
            try:
                result = app.client.conversations_info(channel=channel_id)
                if result["ok"]:
                    channel = result["channel"]
                    return f"#{channel['name']} ({channel_id})"
            except Exception as e:
                logger.error(f"Error fetching channel info: {e}")
                return f"Channel ({channel_id})"
    except Exception as e:
        logger.error(f"Unexpected error in get_channel_info: {e}")
    return channel_id

def format_tasks(user_id):
    if not tasks[user_id]:
        return "No tasks yet. Add some tasks to get started!"
    
    task_list = []
    for task_id, task_info in tasks[user_id].items():
        shared_with = task_info.get("shared_with", [])
        shared_text = ""
        if shared_with:
            shared_names = [get_user_info(user).split(" (")[0] for user in shared_with]
            shared_text = f" (shared with {', '.join(shared_names)})"
        task_list.append(f"• {task_info['text']}{shared_text}")
    
    return "\n".join(task_list)

# Event handler for when the bot is mentioned
@app.event("app_mention")
def handle_mention(event, say):
    try:
        user_info = get_user_info(event['user'])
        channel_info = get_channel_info(event['channel'])
        logger.info(f"Bot mentioned by user {user_info} in channel {channel_info}")
        say(f"Hi <@{event['user']}>! I'm your task tracking bot. How can I help you today?")
    except Exception as e:
        logger.error(f"Error in handle_mention: {e}")

# Command handler for /tasks command
@app.command("/tasks")
def handle_tasks_command(ack, body, say):
    try:
        user_id = body['user_id']
        channel_id = body['channel_id']
        
        # Always acknowledge the command first
        ack()
        
        user_info = get_user_info(user_id)
        channel_info = get_channel_info(channel_id)
        
        logger.info(f"/tasks command received from user {user_info} in channel {channel_info}")
        
        # Format and send the tasks
        task_message = format_tasks(user_id)
        try:
            say(task_message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            # If we can't send the message, try to send it as a DM
            try:
                app.client.chat_postMessage(
                    channel=user_id,
                    text=task_message
                )
            except Exception as dm_error:
                logger.error(f"Error sending DM: {dm_error}")
                
    except Exception as e:
        logger.error(f"Error in handle_tasks_command: {e}")
        try:
            ack()
        except:
            pass

# Command handler for /addtask command
@app.command("/addtask")
def handle_add_task(ack, body, say):
    try:
        user_id = body['user_id']
        text = body['text']
        
        ack()
        
        global task_counter
        task_counter += 1
        tasks[user_id][task_counter] = {"text": text, "shared_with": []}
        
        say(f"Task added! Use `/tasks` to see your tasks.")
        
    except Exception as e:
        logger.error(f"Error in handle_add_task: {e}")
        try:
            ack()
        except:
            pass

# Command handler for /sharetask command
@app.command("/sharetask")
def handle_share_task(ack, body, say):
    try:
        user_id = body['user_id']
        args = body['text'].split()
        
        if len(args) < 2:
            ack("Please provide a task number and user to share with. Example: `/sharetask 1 @username`")
            return
            
        task_id = int(args[0])
        user_to_share = args[1].strip('<>@')
        
        if task_id not in tasks[user_id]:
            ack(f"Task {task_id} not found. Use `/tasks` to see your tasks.")
            return
            
        if "shared_with" not in tasks[user_id][task_id]:
            tasks[user_id][task_id]["shared_with"] = []
            
        if user_to_share not in tasks[user_id][task_id]["shared_with"]:
            tasks[user_id][task_id]["shared_with"].append(user_to_share)
            
        ack()
        say(f"Task shared with <@{user_to_share}>!")
        
    except Exception as e:
        logger.error(f"Error in handle_share_task: {e}")
        try:
            ack()
        except:
            pass

def main():
    logger.info("Starting Slack Task Tracker bot...")
    # Start the app in Socket Mode
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()

if __name__ == "__main__":
    main() 