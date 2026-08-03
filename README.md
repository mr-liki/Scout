# CADDY - Cyberpunk AI Terminal Assistant

A **hacker-style terminal chatbot** with neon effects, ASCII art, and a cyberpunk interface! 🌆⚡

## ✨ Features

- 🎨 **Neon Blue ASCII Logo** - Pixel-style "CADDY" title
- 💚 **Matrix-Style Background** - Animated green hacking screen theme
- ⚡ **Cyberpunk Interface** - Glitch effects and neon colors
- 🤖 **AI Chatbot** - Powered by Hugging Face API
- 🎭 **Typing Effects** - Smooth animations and transitions
- 🔒 **Hacker Aesthetic** - Terminal-style prompts and messages

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Run CADDY

```bash
python main.py
```

### 3. (Optional) Set API Key for Better Performance

```bash
# Get free token from: https://huggingface.co/settings/tokens
export HF_API_KEY='your_token_here'
```

## 🎮 Usage

Once CADDY is running:

- **Chat**: Type your message and press ENTER
- **Clear History**: Type `clear` to reset the conversation
- **Exit**: Type `exit`, `quit`, or press Ctrl+C

## 🎨 Visual Features

### Neon Blue CADDY Logo
```
██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
 ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
```

### Matrix Background
- Animated green characters (binary + Japanese katakana)
- Scrolling hacker-style effects
- Dynamic terminal experience

### Color Scheme
- **Neon Blue (Cyan)**: CADDY logo and borders
- **Neon Green**: Matrix background and user prompt
- **Magenta**: Highlights and accents
- **Yellow**: System messages
- **White**: Chat text

## 📦 Dependencies

- `requests` - API communication
- `colorama` - Terminal colors (cross-platform)
- `pyfiglet` - ASCII art (optional, reserved for extensions)

## 🎯 Example Session

```
[Matrix background scrolling...]

    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ...

[SYSTEM] INITIALIZING NEURAL INTERFACE...
[SYSTEM] CADDY ONLINE - READY FOR INTERACTION

┌─[YOU]
└──> Hello CADDY

┌─[CADDY]
└──> Hello! I'm CADDY, your cyberpunk AI assistant. How can I help you today?

┌─[YOU]
└──> exit

[SYSTEM] DISCONNECTING...
╔═══════════════════════════════════════╗
║  CONNECTION TERMINATED - GOODBYE     ║
╚═══════════════════════════════════════╝
```

## 🔧 Customization

### Change Colors

Edit `main.py` and modify the color constants:

```python
# Logo color
Fore.CYAN  # Change to Fore.GREEN, Fore.MAGENTA, etc.

# Background effect
Fore.GREEN  # The matrix rain color
```

### Adjust Animation Speed

```python
# In print_typing_effect()
time.sleep(0.03)  # Lower = faster, Higher = slower
```

### Use Different AI Model

```python
# In CaddyChatbot.__init__()
self.api_url = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
```

## 🐛 Troubleshooting

### Colors Not Showing

Colorama should work on all platforms, but if issues occur:
```bash
pip install --upgrade colorama
```

### Connection Errors

1. Check your internet connection
2. Wait 10-20 seconds for model to load (first time)
3. Get an API token for better reliability

### Slow Responses

- The first response takes 10-20 seconds (model loading)
- Subsequent responses are faster
- Consider using an API token for priority access

## 🌟 Why CADDY?

- **No Local AI** - Everything runs in the cloud
- **Free Forever** - Hugging Face offers generous free tier
- **Cool Interface** - Stand out from boring chatbots
- **Easy Setup** - Just 3 commands to get started
- **Hackable** - Customize colors, effects, and models

## 📝 License

MIT License - Hack away!

## 🎯 Coming Soon

- [ ] More visual effects
- [ ] Custom themes
- [ ] Voice output
- [ ] Command history
- [ ] Multi-language support

---

**Built with 💚 for terminal lovers and cyberpunk enthusiasts**
