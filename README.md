
# Mod.io downloader GUI
A python script that downloads mod files from mod.io to bypass the "Download mod from game client" message. Made entirely with Google Gemini 2.5 Flash because i dont know how to code. Thus, i likely cant help you with any issues you run into, but you can open an issue anyways. 


## How to use

> Install pip, then Terminal > pip install playwright, then playwright install

>Go to https://mod.io/g and sign in or create an account. 
> In the bottom left, click on your profile picture, select "API Access" and accept the API Access Terms.
> At the bottom, enter a new token name, keep it as Read+Write and click the "+" (plus) icon. Copy the OAuth key it shows you. You will only see this ONCE, which is why the script will save it in a .txt called "oauth_key" for you. Do not delete this file, otherwise youll have to do this again.
> Download, put it into a new folder and run the script (Mod.io-DLGUI.py) and it will ask you for your OAuth key. Paste it in and confirm. 
> Copy the URL of the mod you want to download (ex. https://mod.io/g/drg/m/new-passive-perk-slot#description) and paste it into the downloader, then click "Download Mod". The script will handle the #description part, you do not need to remove it.
> A new folder called "downloaded" will appear in the same location the downloader is in, it contains your mod. 

//i uploaded this as a .py file so you can see for yourself that im not stealing your oauth keys. 
