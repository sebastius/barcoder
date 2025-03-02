import discogs_client
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import paho.mqtt.client as mqtt
import re
import sys
import soco
from soco.plugins.sharelink import ShareLinkPlugin
import time
from soco import discover
import json
import os
import requests
from PIL import Image

script_dir = os.path.dirname(os.path.abspath(__file__))  # Get the directory of the script

CACHE_FILE = "cache.json"

speakers = discover()
woonkamer = next((s for s in speakers if s.player_name == "Woonkamer"), None)

if woonkamer:
    print(f"Found speaker: {woonkamer.player_name} ({woonkamer.ip_address})")
else:
    print("Speaker not found!")

# Replace these with your actual Discogs and Spotify credentials
DISCOGS_TOKEN = 'xxx'
SPOTIFY_CLIENT_ID = 'xxx'
SPOTIFY_CLIENT_SECRET = 'xxx'

# MQTT Broker details
MQTT_BROKER = 'xxx'  # Replace with your broker's address
MQTT_PORT = 1883
MQTT_TOPIC = "barcode/woonkamer/#"
MQTT_USERNAME = 'mqtt'  # Replace with your MQTT username
MQTT_PASSWORD = 'mqtt'  # Replace with your MQTT password

# Initialize the Discogs client
d = discogs_client.Client('MyDiscogsApp/1.0', user_token=DISCOGS_TOKEN)

def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic: {msg.topic}")
    sanitized_string = re.sub(r'[^0-9]', '', msg.payload.decode())
    find_album_on_spotify(sanitized_string)

# Create an MQTT client instance
client = mqtt.Client()

# Callback when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

# Callback when the client disconnects from the broker
def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code {rc}")
    connect_with_retry()

client.on_message = on_message
client.on_connect = on_connect
client.on_disconnect = on_disconnect

# Connect to the broker
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD) 

def connect_with_retry():
    while True:
        try:
            # Connect to the broker
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break  # If connection is successful, break out of the loop
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

connect_with_retry()

# Subscribe to the topic
client.subscribe(MQTT_TOPIC)

def clean_album_title(album_title, artist):
    """Remove artist name from the beginning of the album title if it appears there followed by ' - '."""
    if album_title.startswith(f"{artist} - "):
        album_title = album_title[len(artist) + 3:]  # Remove artist name and " - "
    return album_title

def get_album_from_discogs(upc_code):
    """Search for album information using Discogs API client based on a UPC code."""
    results = d.search(barcode=upc_code, type='release')
    
    # Check if any results were found
    if results:
        release = results[0]  # Get the first result
        album_title = release.title
        artist = release.artists[0].name if release.artists else "Unknown Artist"
        print(f"Found Album: {album_title} by {artist}")
        
        # Clean the album title
        album_title = clean_album_title(album_title, artist)
        
        # Clean the artist
        pattern = r" \(\d+\)$"
        artist = re.sub(pattern, "", artist).strip()
        return album_title, artist
        
    else:
        print("No album found for this UPC.")
        return None, None

def search_album_on_spotify(album_title, artist):
    """Search for an album on Spotify given the album title and artist, printing all results."""
    # Spotify Authentication
    auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # Search for the album on Spotify
    query = f"album:{album_title} artist:{artist}"
    results = sp.search(q=query, type='album', limit=10)  # Increase limit if you want more results
    # Check if any results were found
    if results['albums']['items']:
        album = results['albums']['items'][0]
        return album
    else:
        print("Album not found on Spotify.")
        return None

def send_image(url):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        image = Image.open(response.raw)
        image = image.convert("L")  # "L" mode is 8-bit grayscale
        image.thumbnail((480, 480), Image.LANCZOS)  # Scales longest side to 152
        canvas = Image.new("L", (480, 800), 255)  # 255 = white, 0 = black
        x_offset = (480 - image.width) // 2
        y_offset = 100
        canvas.paste(image, (x_offset, y_offset))
        canvas = canvas.rotate(90, expand=True)
        canvas = canvas.convert("1")  # Convert to black & white
        canvas.save("picture.jpg")
        image_path = os.path.join(script_dir,'picture.jpg')
        mac = '62501F23A3F1C585'
        apip = "192.168.1.162" 
        dither = 0
        url = "http://" + apip + "/imgupload"
        payload = {"dither": dither, "mac": mac}  # Additional POST parameter
        files = {"file": open(image_path, "rb")}  # File to be uploaded
        try:
            response = requests.post(url, data=payload, files=files)
            if response.status_code == 200:
                print(f"{mac} Image uploaded successfully! {image_path}")
            else:
                print(f"{mac} Failed to upload the image.")
        except:
            print(f"{mac} Failed to upload the image.")

        print('succesfully uploaded')

def find_album_on_spotify(upc_code):
    album_title, artist = get_album_from_discogs(upc_code)
    if album_title and artist:
        search_results = search_album_on_spotify(album_title, artist)
        if search_results:
            if woonkamer:
                woonkamer.clear_queue() 
                album_name = search_results['name']
                spotify_url = search_results['external_urls']['spotify']
                share_link = ShareLinkPlugin(woonkamer)
                share_link.add_share_link_to_queue(spotify_url)
                woonkamer.play_from_queue(index=0)
                print(f"Spotify Album sent to player: {album_name} - {spotify_url}")
                album_art_url = search_results['images'][0]['url']
                print(f"URL for artwork: {album_art_url}")
                send_image(album_art_url)
        else:
            print("No albums found on Spotify.")
    else:
        print("Album identification failed.")


if len(sys.argv) > 1:
    barcode = sys.argv[1]  # The first argument is the temperature
    print(f"Received barcode: {barcode}")
    sanitized_string = re.sub(r'[^0-9]', '', barcode)
    find_album_on_spotify(sanitized_string)
else:
    print(f"Listening for messages on topic: {MQTT_TOPIC}...")
    client.loop_forever()



