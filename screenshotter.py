import os
import sys
import time
import keyboard
import pyautogui
from plyer import notification

# Function to clear the console screen for a clean look
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()
print("=== SCREENSHOT CONFIGURATION ===")

# Prompt user inside the console for custom limits (with defaults if they just hit Enter)
try:
    screenshots_input = input("Enter max screenshots limit [Default: 100]: ").strip()
    max_screenshots = int(screenshots_input) if screenshots_input else 100
except ValueError:
    print("Invalid input. Defaulting to 100 screenshots.")
    max_screenshots = 100

try:
    mb_input = input("Enter max storage limit in MB [Default: 100]: ").strip()
    max_folder_size_mb = float(mb_input) if mb_input else 100.0
except ValueError:
    print("Invalid input. Defaulting to 100 MB.")
    max_folder_size_mb = 100.0

# Set the interval in seconds
interval = 0.5

# Your custom absolute file path (fixed to 'Matth')
save_folder = r"C:\Users\Matth\OneDrive\Desktop\PythSC\PythonScreenshots"
os.makedirs(save_folder, exist_ok=True)

# State flag to track whether screenshots are currently being taken
is_running = False

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

def toggle_script():
    """Function triggered automatically whenever 'q' is pressed to start/pause."""
    global is_running
    is_running = not is_running
    if is_running:
        print("\n▶ Script STARTED taking screenshots.")
        send_notification("Screenshotter", "Screenshot capture started.")
    else:
        print("\n⏸ Script PAUSED.")
        send_notification("Screenshotter", "Screenshot capture paused.")

# Register 'q' to toggle start/pause
keyboard.add_hotkey('q', toggle_script)

print("\n--- Screenshot Script is Ready ---")
print(f"📁 Save Location: {save_folder}")
print(f"⚙️ Limits Set: {max_folder_size_mb} MB OR {max_screenshots} screenshots")
print("👉 Press 'q' at any time to START or PAUSE taking screenshots.")
print("👉 Press Ctrl+C in this terminal window to close the program completely.")

count = 1

try:
    while True:
        if is_running:
            # Count existing files and calculate the current size of the folder
            current_folder_size = 0
            file_count = 0
            for root, dirs, files in os.walk(save_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    current_folder_size += os.path.getsize(file_path)
                    file_count += 1
            
            # Convert bytes to Megabytes
            current_folder_size_mb = current_folder_size / (1024 * 1024)

            # Check limits
            if file_count >= max_screenshots:
                print(f"\nScreenshot limit reached ({file_count} / {max_screenshots}). Stopping script...")
                send_notification("Screenshotter", f"Stopped: Reached limit ({max_screenshots} screenshots).")
                is_running = False
                break

            if current_folder_size_mb >= max_folder_size_mb:
                print(f"\nStorage limit reached ({current_folder_size_mb:.2f} MB / {max_folder_size_mb} MB). Stopping script...")
                send_notification("Screenshotter", f"Stopped: Reached storage limit ({max_folder_size_mb} MB).")
                is_running = False
                break

            # Capture and save the screenshot
            screenshot = pyautogui.screenshot()
            filename = os.path.join(save_folder, f"screenshot_{count:03d}.png")
            screenshot.save(filename)
            print(f"Saved: {filename} (Total: {file_count + 1} files, {current_folder_size_mb:.2f} MB)")

            count += 1

            # Wait for the interval duration while checking if paused
            elapsed = 0
            while elapsed < interval and is_running:
                time.sleep(0.1)
                elapsed += 0.1
        else:
            time.sleep(0.1)

except KeyboardInterrupt:
    print("\nProgram closed by user.")
    send_notification("Screenshotter", "Program closed by user.")

print("Screenshot script finished.")