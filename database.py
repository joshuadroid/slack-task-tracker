import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TaskDatabase:
    def __init__(self, db_path="tasks.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize the database with required tables."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create tasks table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed BOOLEAN DEFAULT 0
                    )
                ''')
                
                # Create task_shares table for shared tasks
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS task_shares (
                        task_id INTEGER,
                        shared_with_user_id TEXT NOT NULL,
                        shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (task_id) REFERENCES tasks (id),
                        PRIMARY KEY (task_id, shared_with_user_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def add_task(self, user_id, text):
        """Add a new task for a user."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO tasks (user_id, text) VALUES (?, ?)",
                    (user_id, text)
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            raise

    def get_tasks(self, user_id):
        """Get all tasks for a user, including shared tasks."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Get tasks created by the user
                cursor.execute('''
                    SELECT t.id, t.text, t.completed, t.created_at, 
                           GROUP_CONCAT(ts.shared_with_user_id) as shared_with
                    FROM tasks t
                    LEFT JOIN task_shares ts ON t.id = ts.task_id
                    WHERE t.user_id = ?
                    GROUP BY t.id
                ''', (user_id,))
                own_tasks = cursor.fetchall()

                # Get tasks shared with the user
                cursor.execute('''
                    SELECT t.id, t.text, t.completed, t.created_at, t.user_id as owner_id,
                           GROUP_CONCAT(ts.shared_with_user_id) as shared_with
                    FROM tasks t
                    JOIN task_shares ts ON t.id = ts.task_id
                    WHERE ts.shared_with_user_id = ?
                    GROUP BY t.id
                ''', (user_id,))
                shared_tasks = cursor.fetchall()

                return {
                    'own_tasks': own_tasks,
                    'shared_tasks': shared_tasks
                }
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            raise

    def share_task(self, task_id, user_id, shared_with_user_id):
        """Share a task with another user."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Verify task ownership
                cursor.execute(
                    "SELECT user_id FROM tasks WHERE id = ?",
                    (task_id,)
                )
                task = cursor.fetchone()
                if not task or task[0] != user_id:
                    return False

                # Add share
                cursor.execute(
                    "INSERT INTO task_shares (task_id, shared_with_user_id) VALUES (?, ?)",
                    (task_id, shared_with_user_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error sharing task: {e}")
            raise

    def complete_task(self, task_id, user_id):
        """Mark a task as completed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Verify task ownership or sharing
                cursor.execute('''
                    SELECT t.user_id 
                    FROM tasks t
                    LEFT JOIN task_shares ts ON t.id = ts.task_id
                    WHERE t.id = ? AND (t.user_id = ? OR ts.shared_with_user_id = ?)
                ''', (task_id, user_id, user_id))
                if not cursor.fetchone():
                    return False

                cursor.execute(
                    "UPDATE tasks SET completed = 1 WHERE id = ?",
                    (task_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            raise

    def delete_task(self, task_id, user_id):
        """Delete a task (only owner can delete)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Verify task ownership
                cursor.execute(
                    "SELECT user_id FROM tasks WHERE id = ?",
                    (task_id,)
                )
                task = cursor.fetchone()
                if not task or task[0] != user_id:
                    return False

                # Delete task shares first (due to foreign key constraint)
                cursor.execute(
                    "DELETE FROM task_shares WHERE task_id = ?",
                    (task_id,)
                )
                # Delete the task
                cursor.execute(
                    "DELETE FROM tasks WHERE id = ?",
                    (task_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            raise 