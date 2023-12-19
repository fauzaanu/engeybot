# ENGEYBOT

> NOW MOVED TO: https://github.com/fauzaanu/engeybot-cloudflare/


Engey (އެނގޭ) means knowing in Dhivehi. Bot is live on telegram under the handle of @engeybot

The bot uses openAI completion API to generate responses to user input.

The users are expected to send their queries in the syntax: `why is the sky blue #idk`

As long as #idk is present in the message the bot will try to generate a response.

Why? Because we can then use it in group chats without the bot distrupting the conversation if it is not meant for the bot.

## ADDITIONAL LIBRARIES

we are using edge-tts by rany2 for text to speech. It provides the natural sounding voices on Microsoft Edge and is open source. You can find it from https://github.com/rany2/edge-tts

## Credentials and UsersDB

The bot would need an additional file called cred.py to run.
This is where all our api keys will be stored.

The file should look like this:

```python
# cred.py
# This file is not included in the repo
OPEN_AI_KEY=""
TELEGRAM_API_KEY=""
ADMIN_ID=""
```

Admin_ID is a chat where logs are sent. I do not recommend using your own chat id as it will be spammed with logs. So make a private channel for the logs.

The bot also needs a usersdb.txt file to store all the chat ids of the users it interacts with. This data is collected just incase we need to send a broadcast message to all the users. Create a blank txt file called usersdb and the bot will automatically add the chat ids of the users it interacts with. It will automatically handle the duplicates.

## INSTALLATION

As it is always recommended to make a virtual environment for python projects, we will be using virtualenv for this project. You can install it using pip3 install virtualenv
python3 -m virtualenv venv

Next using virtualenv we can create an environment. For example we will be creating an environment called venv

Next we need to activate the environment. This can be done using source venv/bin/activate if you are on linux or venv\Scripts\activate if you are on windows

The installation is straight forward. You can install the requirements using pip3 install -r req.txt

## Running the bot

No additional settings are required. You can run the bot using python3 bot.py

We use polling as of now and attempts to make it based on webhooks are in progress but not working as of now.

## Contributing

Feel free to contribute to the project / fork the project and make it better. If you have any questions feel free to contact me on telegram or twitter @fauzaanu
