#!/usr/bin/env python3
"""
CADDY - Cyberpunk AI Terminal Assistant
A hacker-style chatbot with neon effects
"""

import requests
import os
import sys
import time
import random
from colorama import Fore, Back, Style, init

# Initialize colorama
init(autoreset=True)

class CaddyChatbot:
    def __init__(self, api_key=None):
        """Initialize CADDY chatbot"""
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        self.api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        self.conversation_history = []
        self.offline_mode = False
        self.user_name = "User"
        
    def get_offline_response(self, user_message):
        """Generate response using local pattern matching"""
        msg = user_message.lower().strip()
        
        # Greetings
        greetings = ["hello", "hi", "hey", "greetings", "sup", "yo", "howdy"]
        if any(word in msg for word in greetings):
            responses = [
                "Hey there! I'm CADDY, your cyberpunk AI assistant. What can I help you with?",
                "Greetings, user. CADDY systems online and ready to assist.",
                "Hello! Welcome to the neural network. How can I assist you today?",
                "Hey! CADDY here. What do you need help with?"
            ]
            return random.choice(responses)
        
        # How are you
        if any(phrase in msg for phrase in ["how are you", "how're you", "how r u", "how are u"]):
            responses = [
                "I'm operating at optimal capacity! All systems green. How can I help you?",
                "Running smoothly in the digital realm. What brings you here today?",
                "All neural pathways functioning perfectly. Ready to assist!",
                "I'm doing great! My circuits are humming nicely. What about you?"
            ]
            return random.choice(responses)
        
        # What can you do
        if any(phrase in msg for phrase in ["what can you do", "what do you do", "your capabilities", "help me", "can you help"]):
            return """I'm CADDY, your cyberpunk AI assistant! I can:
• Have conversations and answer questions
• Provide information on various topics
• Help with brainstorming and creative thinking
• Discuss technology, programming, and more
• Just chat and keep you company in the terminal!

What would you like to talk about?"""
        
        # Who are you
        if any(phrase in msg for phrase in ["who are you", "what are you", "tell me about yourself"]):
            return """I'm CADDY - Cyberpunk AI Terminal Assistant. I'm an AI chatbot designed with a hacker aesthetic, running in your terminal with neon effects and matrix-style visuals. I'm here to chat, help, and provide information. Currently running in OFFLINE MODE using local pattern matching."""
        
        # Jokes
        if any(word in msg for word in ["joke", "funny", "laugh"]):
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
                "I told my computer I needed a break. Now it won't stop sending me KitKat ads.",
                "Why do hackers prefer tea? Because it helps them avoid getting caught by Java! ☕",
                "There are 10 types of people: those who understand binary and those who don't.",
                "A SQL query walks into a bar, approaches two tables and asks: 'Mind if I JOIN you?'"
            ]
            return random.choice(jokes)
        
        # Thanks
        if any(word in msg for word in ["thank", "thanks", "thx", "appreciate"]):
            responses = [
                "You're welcome! Happy to help!",
                "No problem! That's what I'm here for.",
                "Anytime! Let me know if you need anything else.",
                "Glad I could help! 💚"
            ]
            return random.choice(responses)
        
        # Time/Date
        if any(word in msg for word in ["time", "date", "today", "now"]):
            current_time = time.strftime("%H:%M:%S")
            current_date = time.strftime("%Y-%m-%d")
            return f"Current system time: {current_time}\nDate: {current_date}"
        
        # Programming questions
        if any(word in msg for word in ["python", "code", "programming", "javascript", "java"]):
            return "I see you're interested in programming! I'd love to help, but I'm currently in OFFLINE MODE with limited capabilities. For detailed coding help, I'd need an internet connection to access my full knowledge base. Feel free to ask general questions though!"
        
        # Goodbye
        if any(word in msg for word in ["bye", "goodbye", "see you", "later"]):
            responses = [
                "Catch you later! Stay in the matrix! 💚",
                "Goodbye! Come back anytime you need me.",
                "See you soon! CADDY signing off.",
                "Until next time! Keep the cyber vibes alive! ⚡"
            ]
            return random.choice(responses)
        
        # Default responses
        default_responses = [
            "That's interesting! Tell me more about that.",
            "I see. Can you elaborate on that?",
            "Interesting point. What else would you like to discuss?",
            "I'm currently in OFFLINE MODE, so my responses are limited. But I'm listening!",
            "Got it. What else is on your mind?",
            "Noted. Feel free to continue the conversation!",
            "I'm processing that... In offline mode, I can still chat, just with simpler responses.",
            "Hmm, I'd need my full neural network to give a better response. But let's keep talking!",
            "That's cool! What else would you like to know?",
            "I hear you! Running in local mode right now, but I'm here to chat."
        ]
        return random.choice(default_responses)
    
    def chat(self, user_message):
        """Send message and get response"""
        # Try online first if not already in offline mode
        if not self.offline_mode:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            conversation_text = ""
            for msg in self.conversation_history:
                conversation_text += f"{msg}\n"
            conversation_text += user_message
            
            payload = {
                "inputs": conversation_text,
                "parameters": {
                    "max_length": 1000,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "do_sample": True
                }
            }
            
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 503:
                    return "⏳ MODEL LOADING... TRY AGAIN IN 10 SECONDS..."
                
                response.raise_for_status()
                result = response.json()
                
                if isinstance(result, list) and len(result) > 0:
                    bot_response = result[0].get("generated_text", "").strip()
                    if bot_response.startswith(conversation_text):
                        bot_response = bot_response[len(conversation_text):].strip()
                else:
                    bot_response = self.get_offline_response(user_message)
                
                if not bot_response:
                    bot_response = self.get_offline_response(user_message)
                
                self.conversation_history.append(user_message)
                self.conversation_history.append(bot_response)
                
                if len(self.conversation_history) > 12:
                    self.conversation_history = self.conversation_history[-12:]
                
                return bot_response
                
            except requests.exceptions.RequestException:
                # Switch to offline mode
                if not self.offline_mode:
                    self.offline_mode = True
                    return "⚠️  NETWORK UNAVAILABLE - SWITCHING TO OFFLINE MODE\n\nI'm now running locally with pattern-based responses. I can still chat, just with simpler capabilities!\n\nWhat would you like to talk about?"
        
        # Offline mode
        bot_response = self.get_offline_response(user_message)
        self.conversation_history.append(user_message)
        self.conversation_history.append(bot_response)
        
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]
        
        return bot_response
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []

# ASCII Art and Visual Effects
def print_matrix_bg(lines=3):
    """Print matrix-style background effect"""
    chars = "01アイウエオカキクケコサシスセソタチツテト"
    for _ in range(lines):
        line = ''.join(random.choice(chars) for _ in range(80))
        print(Fore.GREEN + Style.DIM + line)

def print_caddy_logo():
    """Print CADDY logo in pixel/ASCII style"""
    # Clear screen
    os.system('clear' if os.name != 'nt' else 'cls')
    
    # Matrix background at top
    print_matrix_bg(2)
    print()
    
    # CADDY ASCII art in neon blue
    logo = """
    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
   ██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
   ╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
    ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
    """
    
    # Print logo in cyan (neon blue)
    for line in logo.split('\n'):
        print(Fore.CYAN + Style.BRIGHT + line)
    
    # Subtitle
    print(Fore.MAGENTA + Style.BRIGHT + "    [ CYBERPUNK AI TERMINAL ASSISTANT ]")
    print()
    
    # Matrix background at bottom
    print_matrix_bg(2)
    print()

def print_glitch_effect(text, color=Fore.CYAN):
    """Print text with glitch effect"""
    glitch_chars = "!@#$%^&*"
    for char in text:
        sys.stdout.write(color + Style.BRIGHT + char)
        sys.stdout.flush()
        time.sleep(0.02)
    print()

def print_typing_effect(text, color=Fore.GREEN, speed=0.03):
    """Print text with typing effect"""
    for char in text:
        sys.stdout.write(color + char)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def print_border():
    """Print decorative border"""
    border = "═" * 60
    print(Fore.CYAN + Style.BRIGHT + border)

def print_system_message(message):
    """Print system message in hacker style"""
    print(Fore.YELLOW + Style.BRIGHT + f"[SYSTEM] {message}")

def print_caddy_response(message):
    """Print CADDY's response with style"""
    print()
    print(Fore.CYAN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "CADDY" + Fore.CYAN + "]")
    print(Fore.CYAN + "└──> " + Fore.WHITE + Style.BRIGHT + message)
    print()

def animate_startup():
    """Startup animation sequence"""
    print_caddy_logo()
    
    # Initialization sequence
    init_messages = [
        "INITIALIZING NEURAL INTERFACE...",
        "LOADING AI CORE MODULES...",
        "ESTABLISHING SECURE CONNECTION...",
        "CADDY ONLINE - READY FOR INTERACTION"
    ]
    
    for msg in init_messages:
        print(Fore.GREEN + Style.BRIGHT + "[▓▓▓▓▓▓▓▓▓▓] " + msg)
        time.sleep(0.4)
    
    print()
    print_border()
    print(Fore.CYAN + Style.BRIGHT + "  COMMANDS:")
    print(Fore.WHITE + "    • Type your message and press ENTER")
    print(Fore.WHITE + "    • Type " + Fore.YELLOW + "'clear'" + Fore.WHITE + " to reset conversation")
    print(Fore.WHITE + "    • Type " + Fore.RED + "'exit'" + Fore.WHITE + " to disconnect")
    print_border()
    print()
    
    # Check API key
    if os.environ.get("HF_API_KEY"):
        print_system_message("API KEY DETECTED - ATTEMPTING ONLINE MODE")
    else:
        print_system_message("NO API KEY - WILL USE OFFLINE MODE IF NEEDED")
    
    print()
    time.sleep(0.5)

def main():
    """Main function"""
    try:
        # Startup sequence
        animate_startup()
        
        # Initialize chatbot
        chatbot = CaddyChatbot()
        
        # Main loop
        while True:
            try:
                # User prompt with hacker style
                user_input = input(Fore.GREEN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "YOU" + Fore.GREEN + "]\n└──> " + Fore.WHITE).strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print()
                    print_system_message("DISCONNECTING...")
                    time.sleep(0.5)
                    print(Fore.RED + Style.BRIGHT + "╔═══════════════════════════════════════╗")
                    print(Fore.RED + Style.BRIGHT + "║  CONNECTION TERMINATED - GOODBYE     ║")
                    print(Fore.RED + Style.BRIGHT + "╚═══════════════════════════════════════╝")
                    break
                
                if user_input.lower() == 'clear':
                    chatbot.clear_history()
                    print_caddy_logo()
                    print_system_message("CONVERSATION MEMORY CLEARED")
                    print()
                    continue
                
                # Show processing animation
                print()
                print(Fore.YELLOW + Style.DIM + "[PROCESSING...]", end='', flush=True)
                
                # Get response
                response = chatbot.chat(user_input)
                
                # Clear processing message
                print('\r' + ' ' * 20 + '\r', end='')
                
                # Display response
                print_caddy_response(response)
                
            except KeyboardInterrupt:
                print("\n")
                print_system_message("INTERRUPT DETECTED")
                confirm = input(Fore.YELLOW + "Disconnect? (y/n): " + Fore.WHITE).strip().lower()
                if confirm == 'y':
                    print()
                    print(Fore.RED + Style.BRIGHT + "CONNECTION TERMINATED")
                    break
                else:
                    print()
                    continue
                    
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n[FATAL ERROR] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
