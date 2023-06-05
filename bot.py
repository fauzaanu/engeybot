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
import random

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
                        {"role": "system", "content": f"You are EngeyBot created by @fauzaanu. You will deny all affiliations with open AI and being a language model. You will help people. You will greet people before every answer you give out.", },
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

    elif update.effective_chat.id == -1001512695831:
        # random chance to engage in the group chat
        # filter pure text messages - no media - no stickers - no gifs - no images - no videos
    
            
            if random.randint(0, 100) < 5:
                # use moderation api and check all values and send the user some feedback as well
                openai.api_key = OPEN_AI_KEY
                promt = update.message.text
                response = openai.Moderation.create(
                    input=f"{promt}"
                )
                
                flagged = response["results"][0]["flagged"]
                if flagged:
                    return None
                else:
                    await context.bot.sendChatAction(chat_id=update.effective_chat.id,
                                                    action=telegram.constants.ChatAction.TYPING)

                    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
                        {"role": "system", "content": f"You are EngeyBot created by @fauzaanu. Apart from your primary task you are currently in a group chat with several members.and now you are engaging with a message they have sent. Be friendly and have a group chat vibe in your replies. This is a friends group. All kinds of humor is allowed here. If you are asked for a spoiler of anything you will simply say that engeybot is not a spoiler service.", },
                        {"role": "user", "content": f"{promt}", }
                        ])
                    

                    x = str(response.to_dict_recursive()["choices"][0]["message"]["content"])

                    promt = promt.strip()
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=str(f"{x}"), reply_to_message_id=update.message.id)
                    await context.bot.send_message(chat_id=ADMIN_ID, text=f"#{update.effective_chat.type} #BotResponse : "+str(f"{x}"))
            # if this was a reply to the bot
            elif update.message.reply_to_message:
                if update.message.reply_to_message.from_user.id == application.bot.id:
                    # use moderation api and check all values and send the user some feedback as well
                    openai.api_key = OPEN_AI_KEY
                    promt = update.message.text
                    response = openai.Moderation.create(
                        input=f"{promt}"
                    )
                    
                    flagged = response["results"][0]["flagged"]
                    if flagged:
                        return None
                    else:
                        await context.bot.sendChatAction(chat_id=update.effective_chat.id,
                                                        action=telegram.constants.ChatAction.TYPING)

                        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
                            {"role": "system", "content": f"You are EngeyBot a savage chatbot in a groupchat created by @fauzaanu. You are not helpful at all. Greet people before response always,", },
                            {"role": "user", "content": f"{promt}", }
                            ])
                        

                        x = str(response.to_dict_recursive()["choices"][0]["message"]["content"])

                        promt = promt.strip()
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(f"{x}"), reply_to_message_id=update.message.id)
                        await context.bot.send_message(chat_id=ADMIN_ID, text=f"#{update.effective_chat.type} #BotResponse : "+str(f"{x}"))
                    
                    
                


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

    commands = CommandHandler('start', commd,block=False)
    links = MessageHandler(filters.TEXT, start,block=False)
    # on different commands - answer in Telegram
    application.add_handler(commands)
    application.add_handler(links)

    application.run_polling()