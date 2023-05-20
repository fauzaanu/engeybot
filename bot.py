import time
import openai
import logging
import telegram
from telegram import Update
from telegram.ext import ContextTypes
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler
from cred import *
from tts import _main
import os

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_qry = update.message.text
    await context.bot.send_message(chat_id=ADMIN_ID, text=update)
    
    
    with open("usersdb.txt", "r") as f:
        status = False
        for line in f:
            if str(update.effective_chat.id) in line:
                status = True
                break
        
        if status == False:
            with open("usersdb.txt", "a") as f:
                f.write(str(update.effective_chat.id)+"\n")
    
    # check if it is a group or a private chat
    if update.effective_chat.type == "private" or (update.effective_chat.type == "group" and "#idk" in bot_qry.lower()) or (update.effective_chat.type == "supergroup" and "#idk" in bot_qry.lower()):
        # Load your API key from an environment variable or secret management service
        openai.api_key = OPEN_AI_KEY
        promt = bot_qry.replace('#idk', '')
        firstname = update.effective_user.first_name
        
        # in supergroups and groups, the first name is not available
        if update.effective_chat.type == "supergroup" or update.effective_chat.type == "group":
            firstname = update.effective_message.from_user.first_name
        print(firstname)
        
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"#{update.effective_chat.type}: "+str(update))

        if len(promt) < 4000:
            # use moderation api and check all values and send the user some feedback as well
            response = openai.Moderation.create(
                input=f"{promt}"
            )
            
            flagged = response["results"][0]["flagged"]
            if flagged:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=str(f"Your Request was flagged!"), reply_to_message_id=update.message.id)
            else:

                await context.bot.sendChatAction(chat_id=update.effective_chat.id,
                                                 action=telegram.constants.ChatAction.TYPING)

                response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
                    {"role": "system", "content": f"You are EngeyBot created by @fauzaanu to help {firstname} with a question they have. Your job is to provide him every piece of knowledge you can about the subject matter {firstname} asked. You are programmed to replicate and match the energy or emotion that {firstname} asks their question with when providing your genius and brilliant answer. You are also programmed to greet the individual with their name (in this case the name is {firstname}) in a warm and fun greeting before giving the answer.", },
                    {"role": "user", "content": f"{promt}", }
                    ])
                

                x = str(response.to_dict_recursive()["choices"][0]["message"]["content"])

                promt = promt.strip()
                await context.bot.send_message(chat_id=update.effective_chat.id, text=str(f"{x}"), reply_to_message_id=update.message.id)
                
                tts_string = str(f"{x}")
                
                await _main(str(tts_string))
                # check if the file exists

                if os.path.exists("voice.mp3"):
                    await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open('voice.mp3', 'rb'), title=f"{promt}", performer=f"@EngeyBot", caption=f"{promt}", thumb="main.jpg", reply_to_message_id=update.message.id)
                    
                    os.remove("voice.mp3")
                
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"#{update.effective_chat.type} #BotResponse : "+str(f"{x}"))
                
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="1000 characters allowed")

    


# working part
async def commd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=ADMIN_ID, text="#newuser: "+str(update))
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Please send your questions in the following format: <your question> #idk")
    
    with open("usersdb.txt", "r") as f:
        status = False
        for line in f:
            if str(update.effective_chat.id) in line:
                status = True
                break
        
        if status == False:
            with open("usersdb.txt", "a") as f:
                f.write(str(update.effective_chat.id)+"\n")


if __name__ == '__main__':
    token = TELEGRAM_API_KEY
    
    
    # # webhook transition  -- failing for some reason
    # url = "https://engeybot.fauzaanu.com"
    # port = 8000
    
    # https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks
    # openssl req -newkey rsa:2048 -sha256 -noenc -keyout private.key -x509 -days 3650 -out cert.pem
    
    
    application = ApplicationBuilder().token(token).build()

    commands = CommandHandler('start', commd)
    links = MessageHandler(filters.TEXT, start)
    # on different commands - answer in Telegram
    application.add_handler(commands)
    application.add_handler(links)

    application.run_polling()