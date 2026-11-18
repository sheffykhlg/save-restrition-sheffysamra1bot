import certifi
from pymongo import MongoClient
from core.config import MONGO_URI

mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client["telegram_bot_db"]

sessions_col = db["user_sessions"]
replace_rules_col = db["user_replace_rules"]
bot_meta_col = db["bot_metadata"]
user_chats_col = db["user_chats"]
bot_users_col = db["bot_users"]
batch_jobs_col = db["batch_jobs"]

