#!/usr/bin/env python3
"""
Simple Terminal Chatbot using Hugging Face Inference API
A conversational chatbot that runs in your terminal
"""

import requests
import json
import sys
import os

class SimpleChatbot:
    def __init__(self, api_key=None):
        """
        Initialize the chatbot with Hugging Face API configuration
        
        Args:
            api_key: Hugging Face API token (optional, can use env variable)
        """
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        # Using Meta's Llama model via Hugging Face (free tier available)
        self.api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        self.conversation_history = []
        
    def chat(self, user_message):
        """
        Send a message to the chatbot and get a response
        
        Args:
            user_message: The user's input message
            
        Returns:
            The chatbot's response
        """
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Build the conversation context
        conversation_text = ""
        for i, msg in enumerate(self.conversation_history):
            if i % 2 == 0:
                conversation_text += f"{msg}\n"
            else:
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
                timeout=30
            )
            
            if response.status_code == 503:
                return "⏳ Model is loading, please wait a moment and try again..."
            
            response.raise_for_status()
            
            result = response.json()
            
            # Handle different response formats
            if isinstance(result, list) and len(result) > 0:
                bot_response = result[0].get("generated_text", "").strip()
                # Remove the input from the response if it's included
                if bot_response.startswith(conversation_text):
                    bot_response = bot_response[len(conversation_text):].strip()
            elif isinstance(result, dict):
                bot_response = result.get("generated_text", "Sorry, I couldn't generate a response.").strip()
            else:
                bot_response = "Sorry, I received an unexpected response format."
            
            # Clean up the response
            if not bot_response:
                bot_response = "I'm not sure how to respond to that. Could you rephrase?"
            
            # Update conversation history
            self.conversation_history.append(user_message)
            self.conversation_history.append(bot_response)
            
            # Keep only last 6 exchanges to avoid context getting too long
            if len(self.conversation_history) > 12:
                self.conversation_history = self.conversation_history[-12:]
            
            return bot_response
            
        except requests.exceptions.RequestException as e:
            return f"❌ Error communicating with API: {str(e)}"
        except Exception as e:
            return f"❌ Unexpected error: {str(e)}"
    
    def clear_history(self):
        """Clear the conversation history"""
        self.conversation_history = []
        print("Conversation history cleared!")

def print_welcome():
    """Print welcome message and instructions"""
    print("=" * 60)
    print("🤖 Simple Terminal Chatbot (Hugging Face API)")
    print("=" * 60)
    print("Commands:")
    print("  - Type your message and press Enter to chat")
    print("  - Type 'clear' to clear conversation history")
    print("  - Type 'exit' or 'quit' to end the conversation")
    print("=" * 60)
    print()

def main():
    """Main function to run the chatbot"""
    print_welcome()
    
    # Check for API key
    api_key = os.environ.get("HF_API_KEY")
    if not api_key:
        print("💡 Tip: For better rate limits, set HF_API_KEY environment variable")
        print("   Get a free token at: https://huggingface.co/settings/tokens")
        print("   Export it: export HF_API_KEY='your_token_here'\n")
    else:
        print("✓ Hugging Face API key detected!\n")
    
    # Initialize chatbot
    chatbot = SimpleChatbot(api_key)
    
    print("🚀 Chatbot ready! (First response may take a few seconds)\n")
    
    # Main chat loop
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()
            
            # Handle empty input
            if not user_input:
                continue
            
            # Handle commands
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\n👋 Goodbye! Have a great day!")
                break
            
            if user_input.lower() == 'clear':
                chatbot.clear_history()
                continue
            
            # Get chatbot response
            print("Bot: ", end="", flush=True)
            response = chatbot.chat(user_input)
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye! Have a great day!")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {str(e)}")
            print("Please try again.\n")

if __name__ == "__main__":
    main()
