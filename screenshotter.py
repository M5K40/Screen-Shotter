import os
import sys
import time
import keyboard
import pyautogui
from plyer import notification

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()
print("=== SCREENSHOT CONFIGURATION ===")

# 1. Force the user to enter a valid, existing base directory (No default allowed)
while True:
    dir_input = input("Enter base save folder path (Required): ").strip()
    dir_input = dir_input.strip('"').strip("'")

    if not dir_input:
        print("❌ Error: A folder path is required. Please enter a valid directory.\n")
        continue

    if os.path.isdir(dir_input):
        base_dir = dir_input
        break
    else:
        print(f"❌ Error: '{dir_input}' does not exist or is not a valid folder. Please try again.\n")

# 2. Ask for max screenshots limit
try:
    screenshots_input = input("Enter max screenshots limit [Default: 100]: ").strip()
    max_screenshots = int(screenshots_input) if screenshots_input else 100
except ValueError:
    print("Invalid input. Defaulting to 100 screenshots.")
    max_screenshots = 100

# 3. Ask for max storage limit
try:
    mb_input = input("Enter max storage limit in MB [Default: 100]: ").strip()
    max_folder_size_mb = float(mb_input) if mb_input else 100.0
except ValueError:
    print("Invalid input. Defaulting to 100 MB.")
    max_folder_size_mb = 100.0

# 4. Ask for delay between screenshots (Default: 0.5 seconds)
try:
    interval_input = input("Enter delay between screenshots in seconds [Default: 0.5]: ").strip()
    interval = float(interval_input) if interval_input else 0.5
    if interval <= 0:
        raise ValueError
except ValueError:
    print("Invalid input. Defaulting to 0.5 seconds.")
    interval = 0.5

# 5. Ask for custom start/pause toggle keybind (Default: 'q')
while True:
    toggle_key_input = input("Enter keybind to START/PAUSE continuous capture [Default: q]: ").strip().lower()
    toggle_hotkey = toggle_key_input if toggle_key_input else 'q'

    try:
        keyboard.parse_hotkey(toggle_hotkey)
        break
    except ValueError:
        print(f"❌ Error: '{toggle_hotkey}' is not a valid key (e.g., try 'q', 'f8', or 'ctrl+alt+s').\n")

# 6. Ask for custom single-screenshot keybind (Default: 'e')
while True:
    single_key_input = input("Enter keybind for taking 1 screenshot [Default: e]: ").strip().lower()
    single_hotkey = single_key_input if single_key_input else 'e'

    if single_hotkey == toggle_hotkey:
        print(f"❌ Error: '{single_hotkey}' is already used to start/pause. Pick a different key.\n")
        continue

    try:
        keyboard.parse_hotkey(single_hotkey)
        break
    except ValueError:
        print(f"❌ Error: '{single_hotkey}' is not a valid key (e.g., try 'e', 'f9', or 'ctrl+shift+s').\n")

# 7. Ask for custom quit keybind (Default: ')
while True:
    quit_key_input = input("Enter keybind to completely quit the script [Default: ']: ").strip().lower()
    quit_hotkey = quit_key_input if quit_key_input else "'"

    if quit_hotkey in (toggle_hotkey, single_hotkey):
        print(f"❌ Error: '{quit_hotkey}' is already assigned to another action. Pick a different key.\n")
        continue

    try:
        keyboard.parse_hotkey(quit_hotkey)
        break
    except ValueError:
        print(f"❌ Error: '{quit_hotkey}' is not a valid key (e.g., try ', 'esc', or 'ctrl+q').\n")

# Find the next available numbered folder inside the validated base_dir
folder_num = 1
while True:
    save_folder = os.path.join(base_dir, f"PythonScreenshots{folder_num}")
    if not os.path.exists(save_folder):
        try:
            os.makedirs(save_folder)
            break
        except OSError as e:
            print(f"❌ Fatal Error: Cannot write to '{base_dir}' ({e}). Exiting...")
            sys.exit(1)
    folder_num += 1

is_running = False
stop_script = False
count = 1

def send_notification(title, message):
    """Helper function to send a desktop notification."""
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Screenshotter",
            timeout=2
        )
    except Exception as e:
        print(f"Could not send notification: {e}")

def take_screenshot(manual=False):
    """Checks limits and captures a single screenshot."""
    global count, is_running, stop_script

    if stop_script:
        return False

    current_folder_size = 0
    file_count = 0
    for root, dirs, files in os.walk(save_folder):
        for file in files:
            file_path = os.path.join(root, file)
            current_folder_size += os.path.getsize(file_path)
            file_count += 1

    current_folder_size_mb = current_folder_size / (1024 * 1024)

    if file_count >= max_screenshots:
        print(f"\nScreenshot limit reached ({file_count} / {max_screenshots}). Stopping script...")
        send_notification("Screenshotter", f"Stopped: Reached limit ({max_screenshots} screenshots).")
        is_running = False
        stop_script = True
        return False

    if current_folder_size_mb >= max_folder_size_mb:
        print(f"\nStorage limit reached ({current_folder_size_mb:.2f} MB / {max_folder_size_mb} MB). Stopping script...")
        send_notification("Screenshotter", f"Stopped: Reached storage limit ({max_folder_size_mb} MB).")
        is_running = False
        stop_script = True
        return False

    screenshot = pyautogui.screenshot()
    filename = os.path.join(save_folder, f"screenshot_{count:03d}.png")
    screenshot.save(filename)

    tag = "[Manual] " if manual else ""
    print(f"{tag}Saved: {filename} (Total: {file_count + 1} files, {current_folder_size_mb:.2f} MB)")

    if manual:
        send_notification("Screenshotter", f"Captured screenshot_{count:03d}.png")

    count += 1
    return True

def toggle_script():
    """Toggles continuous screenshot mode on or off."""
    global is_running
    if stop_script:
        return
    is_running = not is_running
    if is_running:
        print("\n▶ Continuous capture STARTED.")
        send_notification("Screenshotter", "Continuous capture started.")
    else:
        print("\n⏸ Continuous capture PAUSED.")
        send_notification("Screenshotter", "Continuous capture paused.")

def single_shot():
    """Captures a single screenshot when the custom hotkey is pressed."""
    take_screenshot(manual=True)

def quit_script():
    """Signals the main loop to exit and closes the program."""
    global is_running, stop_script
    if not stop_script:
        is_running = False
        stop_script = True
        print(f"\n🛑 Quit hotkey ('{quit_hotkey}') pressed. Exiting...")
        send_notification("Screenshotter", "Program closed by user.")

# Register hotkeys
keyboard.add_hotkey(toggle_hotkey, toggle_script)
keyboard.add_hotkey(single_hotkey, single_shot)
keyboard.add_hotkey(quit_hotkey, quit_script)

print("\n--- Screenshot Script is Ready ---")
print(f"📁 Save Location: {save_folder}")
print(f"⚙️ Limits Set: {max_folder_size_mb} MB OR {max_screenshots} screenshots | Delay: {interval}s")
print(f"👉 Press '{toggle_hotkey}' to START or PAUSE continuous screenshots.")
print(f"👉 Press '{single_hotkey}' to take a SINGLE screenshot.")
print(f"👉 Press '{quit_hotkey}' to QUIT the program completely.")

try:
    while not stop_script:
        if is_running:
            if not take_screenshot(manual=False):
                break

            elapsed = 0
            while elapsed < interval and is_running and not stop_script:
                time.sleep(0.1)
                elapsed += 0.1
        else:
            time.sleep(0.1)

except KeyboardInterrupt:
    print("\nProgram closed by user.")
    send_notification("Screenshotter", "Program closed by user.")
finally:
    keyboard.unhook_all()

print("Screenshot script finished.")
