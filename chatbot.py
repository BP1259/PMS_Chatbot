"""
chatbot.py — CLI RAG Chatbot with intent-aware responses
Usage: python chatbot.py
"""

import os, sys
from colorama import Fore, Style, init
from dotenv import load_dotenv

load_dotenv()
init(autoreset=True)

from rag_engine import get_secret, ask, make_fw_client, chunk_count

BANNER = f"""
{Fore.GREEN}{'═'*58}
  🤖  BP PMS Appraisal Chatbot — DeepSeek V4 Pro
  📊  Ask anything about the Performance Appraisal System
{'═'*58}{Style.RESET_ALL}
Commands: {Fore.YELLOW}/sources /clear /quit{Style.RESET_ALL}
"""

def print_sources(sources):
    if not sources:
        print(f"  {Fore.CYAN}(answered from general knowledge — no chunks retrieved){Style.RESET_ALL}")
        return
    print(f"\n{Fore.CYAN}📎 Retrieved:{Style.RESET_ALL}")
    for i, s in enumerate(sources, 1):
        bar = "█" * int(s.get("relevance", 0) * 15)
        print(f"   {i}. Step {s.get('step_number','N/A')} · {s.get('step_title','General')}"
              f"  {Fore.CYAN}{bar}{Style.RESET_ALL} {s.get('relevance',0):.0%}")

def main():
    api_key = get_secret("FIREWORKS_API_KEY")
    db_url  = get_secret("SUPABASE_DB_URL")

    if not api_key:
        print(f"{Fore.RED}❌ FIREWORKS_API_KEY not set in .env{Style.RESET_ALL}")
        sys.exit(1)
    if not db_url:
        print(f"{Fore.RED}❌ SUPABASE_DB_URL not set in .env{Style.RESET_ALL}")
        sys.exit(1)

    print(BANNER)
    try:
        n = chunk_count()
        print(f"{Fore.GREEN}✅ Supabase: {n} chunks ready{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ DB error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    fw_client    = make_fw_client(api_key)
    history      = []
    show_sources = True

    while True:
        try:
            user_input = input(f"\n{Fore.YELLOW}You › {Style.RESET_ALL}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.GREEN}Goodbye!{Style.RESET_ALL}")
            break

        if not user_input:
            continue
        if user_input.lower() == "/quit":
            break
        elif user_input.lower() == "/clear":
            history = []
            print(f"{Fore.CYAN}🔄 Cleared.{Style.RESET_ALL}")
            continue
        elif user_input.lower() == "/sources":
            show_sources = not show_sources
            print(f"{Fore.CYAN}Sources: {'ON' if show_sources else 'OFF'}{Style.RESET_ALL}")
            continue

        print(f"{Fore.CYAN}⏳ Thinking...{Style.RESET_ALL}", end="\r")
        try:
            answer, sources = ask(fw_client, user_input, history)
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}")
            continue

        print(" " * 25 + "\r", end="")
        print(f"\n{Fore.GREEN}Bot ›{Style.RESET_ALL} {answer}")

        if show_sources:
            print_sources(sources)

        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": answer})

if __name__ == "__main__":
    main()
