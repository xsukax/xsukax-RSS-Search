#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xsukax RSS Search Launcher
==========================

Simple launcher script that handles dependency checking,
initial setup, and graceful error handling for the GUI application.

This script:
- Checks for required dependencies
- Offers to install missing packages
- Provides helpful error messages
- Sets up the initial environment
- Launches the main GUI application
"""

import sys
import os
import subprocess
import importlib.util

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 6):
        print("Error: Python 3.6 or higher is required.")
        print(f"Current version: {sys.version}")
        print("Please upgrade Python and try again.")
        return False
    return True

def check_dependency(package_name, import_name=None):
    """Check if a package is installed."""
    if import_name is None:
        import_name = package_name
    
    spec = importlib.util.find_spec(import_name)
    return spec is not None

def install_package(package_name):
    """Install a package using pip."""
    try:
        print(f"Installing {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✓ Successfully installed {package_name}")
            return True
        else:
            print(f"✗ Failed to install {package_name}")
            print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ Error installing {package_name}: {e}")
        return False

def check_and_install_dependencies():
    """Check for and install missing dependencies."""
    dependencies = [
        ("feedparser", "feedparser"),
        ("requests", "requests"),
        ("tkinter", "tkinter")  # Usually built-in
    ]
    
    missing_packages = []
    
    print("Checking dependencies...")
    
    for package_name, import_name in dependencies:
        if check_dependency(package_name, import_name):
            print(f"✓ {package_name}")
        else:
            print(f"✗ {package_name} (missing)")
            if package_name != "tkinter":  # tkinter should be built-in
                missing_packages.append(package_name)
    
    if missing_packages:
        print("\nMissing packages detected.")
        response = input("Would you like to install them automatically? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            all_installed = True
            for package in missing_packages:
                if not install_package(package):
                    all_installed = False
            
            if not all_installed:
                print("\nSome packages failed to install. Please install them manually:")
                for package in missing_packages:
                    print(f"  pip install {package}")
                return False
        else:
            print("\nPlease install the missing packages manually:")
            for package in missing_packages:
                print(f"  pip install {package}")
            return False
    
    # Special check for tkinter
    if not check_dependency("tkinter", "tkinter"):
        print("\n⚠️  Warning: tkinter is not available.")
        print("This is unusual as tkinter should be included with Python.")
        print("Please check your Python installation or install tkinter manually.")
        return False
    
    return True

def setup_initial_files():
    """Set up initial configuration files if they don't exist."""
    feeds_file = "feeds.txt"
    
    if not os.path.exists(feeds_file):
        print(f"\nCreating sample {feeds_file}...")
        
        sample_feeds = """# xsukax RSS Search - Feed Configuration
# Add one RSS/Atom feed URL per line
# Lines starting with # are comments

# News Sources
https://feeds.bbci.co.uk/news/rss.xml
http://rss.cnn.com/rss/edition.rss
https://feeds.reuters.com/reuters/topNews

# Technology News
https://feeds.feedburner.com/TechCrunch
https://rss.slashdot.org/Slashdot/slashdot

# Uncomment and edit these examples:
# https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
# https://feeds.washingtonpost.com/rss/national
"""
        
        try:
            with open(feeds_file, "w", encoding="utf-8") as f:
                f.write(sample_feeds)
            print(f"✓ Created {feeds_file} with sample feeds")
            print("  Edit this file to add your preferred RSS feeds")
        except Exception as e:
            print(f"✗ Failed to create {feeds_file}: {e}")

def launch_gui():
    """Launch the main GUI application."""
    try:
        print("\nLaunching xsukax RSS Search GUI...")
        
        # Try to import and run the GUI
        try:
            from xsukax_gui import MainApplication
            app = MainApplication()
            app.run()
            
        except ImportError:
            # Fallback: try to run as script
            if os.path.exists("xsukax_rss_search_gui.py"):
                subprocess.run([sys.executable, "xsukax_rss_search_gui.py"])
            else:
                print("✗ GUI application file not found!")
                print("Please ensure xsukax_rss_search_gui.py is in the current directory.")
                return False
                
    except Exception as e:
        print(f"✗ Failed to launch GUI: {e}")
        print("\nTroubleshooting tips:")
        print("1. Ensure all files are in the same directory")
        print("2. Check that Python has GUI support (tkinter)")
        print("3. Try running: python xsukax_rss_search_gui.py")
        return False
    
    return True

def main():
    """Main launcher function."""
    print("=" * 50)
    print("xsukax RSS Search - GUI Launcher")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        input("\nPress Enter to exit...")
        return 1
    
    # Check and install dependencies
    if not check_and_install_dependencies():
        input("\nPress Enter to exit...")
        return 1
    
    # Set up initial files
    setup_initial_files()
    
    # Launch GUI
    if not launch_gui():
        input("\nPress Enter to exit...")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
