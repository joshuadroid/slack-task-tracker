import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from database import TaskDatabase
import json

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

# Initialize database
db = TaskDatabase()

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
    try:
        tasks = db.get_tasks(user_id)
        
        if not tasks['own_tasks'] and not tasks['shared_tasks']:
            return "No tasks yet. Add some tasks to get started!"
        
        message_parts = []
        
        # Format own tasks
        if tasks['own_tasks']:
            message_parts.append("*Your Tasks:*")
            for task in tasks['own_tasks']:
                task_id, text, completed, created_at, shared_with = task
                status = "✅" if completed else "🚧"
                shared_text = ""
                if shared_with:
                    shared_names = [get_user_info(user).split(" (")[0] for user in shared_with.split(",")]
                    shared_text = f" (shared with {', '.join(shared_names)})"
                message_parts.append(f"{status} {text} (ID: {task_id}){shared_text}")
        
        # Format shared tasks
        if tasks['shared_tasks']:
            message_parts.append("\n*Tasks Shared With You:*")
            for task in tasks['shared_tasks']:
                task_id, text, completed, created_at, owner_id, shared_with = task
                status = "✅" if completed else "🚧"
                owner_name = get_user_info(owner_id).split(" (")[0]
                message_parts.append(f"{status} {text} (ID: {task_id}, from {owner_name})")
        
        return "\n".join(message_parts)
    except Exception as e:
        logger.error(f"Error formatting tasks: {e}")
        return "Error retrieving tasks. Please try again."

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
def handle_add_task(ack, command, body, logger):
    ack()
    try:
        # Log the raw message body
        logger.info(f"📦 Raw Slack message body: {json.dumps(body, indent=2)}")
        
        user_id = body['user_id']
        text = command['text']
        
        if not text:
            ack("Please provide a task description. Example: `/addtask Buy groceries`")
            return
        
        task_id = db.add_task(user_id, text)
        user_info = get_user_info(user_id)
        logger.info(f"📝 New task added by {user_info}: '{text}' (ID: {task_id})")
        ack()
        say(f"Task added! (ID: {task_id}) Use `/tasks` to see your tasks.")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_add_task: {e}")
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
            
        try:
            task_id = int(args[0])
        except ValueError:
            ack("Please provide a valid task number.")
            return
            
        user_to_share = args[1].strip('<>@')
        
        if db.share_task(task_id, user_id, user_to_share):
            ack()
            say(f"Task shared with <@{user_to_share}>!")
        else:
            ack("Task not found or you don't have permission to share it.")
        
    except Exception as e:
        logger.error(f"Error in handle_share_task: {e}")
        try:
            ack()
        except:
            pass

# Command handler for /completetask command
@app.command("/completetask")
def handle_complete_task(ack, body, say):
    try:
        user_id = body['user_id']
        args = body['text'].split()
        
        if not args:
            ack("Please provide a task number. Example: `/completetask 1`")
            return
            
        try:
            task_id = int(args[0])
        except ValueError:
            ack("Please provide a valid task number.")
            return
        
        if db.complete_task(task_id, user_id):
            user_info = get_user_info(user_id)
            logger.info(f"✅ Task {task_id} marked as completed by {user_info}")
            ack()
            say(f"Task marked as completed! Use `/tasks` to see your updated task list.")
        else:
            logger.warning(f"⚠️ Failed to complete task {task_id} - Not found or no permission")
            ack("Task not found or you don't have permission to complete it.")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_complete_task: {e}")
        try:
            ack()
        except:
            pass

# Command handler for /deletetask command
@app.command("/deletetask")
def handle_delete_task(ack, body, say):
    try:
        user_id = body['user_id']
        args = body['text'].split()
        
        if not args:
            ack("Please provide a task number. Example: `/deletetask 1`")
            return
            
        try:
            task_id = int(args[0])
        except ValueError:
            ack("Please provide a valid task number.")
            return
        
        if db.delete_task(task_id, user_id):
            user_info = get_user_info(user_id)
            logger.info(f"🗑️ Task {task_id} deleted by {user_info}")
            ack()
            say(f"Task deleted! Use `/tasks` to see your updated task list.")
        else:
            logger.warning(f"⚠️ Failed to delete task {task_id} - Not found or no permission")
            ack("Task not found or you don't have permission to delete it.")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_delete_task: {e}")
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