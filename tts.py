import asyncio
import edge_tts
import random




    

async def _main(text:str, voice="en-GB-SoniaNeural",output="voice.mp3") -> None:
    
    voices = await edge_tts.VoicesManager.create()
    voice = voices.find(Gender="Female", Language="en")
    # Also supports Locales
    # voice = voices.find(Gender="Female", Locale="es-AR")

    final_voice = random.choice(voice)["Name"]
    print(final_voice)
    
    communicate = edge_tts.Communicate(text, final_voice)
    await communicate.save(output)
    


if __name__ == "__main__":
    TEXT = "The dealer is not technically something new. The concept was first illustraded by steve on the 2012 Bootcamp. The dealer is just a much wider and smarter implementation of the same concept."
    VOICE = "en-GB-SoniaNeural"
    OUTPUT_FILE = "test.mp3"
    asyncio.get_event_loop().run_until_complete(_main(text=TEXT, voice=VOICE, output=OUTPUT_FILE))