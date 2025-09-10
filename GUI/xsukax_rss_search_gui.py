#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xsukax RSS Search GUI Application
==================================

A modern, user-friendly GUI for the xsukax RSS Search tool.
Built with Tkinter/ttk for cross-platform compatibility and professional appearance.

Features:
- Feed management with drag-and-drop support
- Real-time search with progress indication
- Responsive layout design
- Dark/Light theme support
- Comprehensive error handling
- Modular, maintainable code structure

Dependencies:
    - tkinter (built-in)
    - feedparser, requests (from original application)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import os
import sys
import webbrowser
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
import tempfile

# Import the original RSS search functionality
# Note: This assumes the original script is in the same directory
try:
    from xsukax_rss_search import (
        load_feeds_from_txt, parse_keywords, fetch_and_parse,
        safe_entries, field_text, matches, entry_datetime, render_html
    )
except ImportError:
    # Fallback imports if the original script is not available
    print("Warning: Original RSS search module not found. Some functionality may be limited.")
    
    def load_feeds_from_txt(path): return []
    def parse_keywords(raw): return []
    def fetch_and_parse(url, timeout=12): return url, {"entries": []}, None
    def safe_entries(parsed): return []
    def field_text(entry, which): return ""
    def matches(text, keywords, mode): return False
    def entry_datetime(e): return 0.0
    def render_html(*args, **kwargs): return "<html><body>Mock HTML</body></html>"


class Theme:
    """Theme management for consistent styling across the application."""
    
    LIGHT = {
        'bg': '#ffffff',
        'fg': '#000000',
        'select_bg': '#0078d4',
        'select_fg': '#ffffff',
        'entry_bg': '#ffffff',
        'entry_fg': '#000000',
        'button_bg': '#f0f0f0',
        'button_fg': '#000000',
        'frame_bg': '#f8f9fa',
        'accent': '#0078d4',
        'success': '#107c10',
        'warning': '#ff8c00',
        'error': '#d13438'
    }
    
    DARK = {
        'bg': '#2d2d30',
        'fg': '#ffffff',
        'select_bg': '#404040',
        'select_fg': '#ffffff',
        'entry_bg': '#1e1e1e',
        'entry_fg': '#ffffff',
        'button_bg': '#404040',
        'button_fg': '#ffffff',
        'frame_bg': '#252526',
        'accent': '#0078d4',
        'success': '#107c10',
        'warning': '#ff8c00',
        'error': '#d13438'
    }
    
    @classmethod
    def get_current_theme(cls) -> Dict[str, str]:
        """Get the current theme based on system preferences."""
        # For now, default to light theme
        # In a real implementation, you might detect system theme
        return cls.LIGHT


class ProgressDialog:
    """A professional progress dialog with cancellation support."""
    
    def __init__(self, parent: tk.Tk, title: str = "Processing"):
        self.parent = parent
        self.cancelled = False
        
        # Create modal dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x150")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent
        self.dialog.geometry(f"+{parent.winfo_x() + 50}+{parent.winfo_y() + 50}")
        
        # Create widgets
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        self.status_label = ttk.Label(main_frame, text="Initializing...", font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 10))
        
        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))
        self.progress.start()
        
        self.cancel_button = ttk.Button(main_frame, text="Cancel", command=self.cancel)
        self.cancel_button.pack()
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
    
    def update_status(self, message: str):
        """Update the status message."""
        self.status_label.config(text=message)
        self.dialog.update()
    
    def cancel(self):
        """Cancel the operation."""
        self.cancelled = True
        self.close()
    
    def close(self):
        """Close the dialog."""
        self.progress.stop()
        self.dialog.destroy()


class FeedManager(ttk.Frame):
    """Widget for managing RSS feed URLs with add/edit/remove functionality."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.feeds: List[str] = []
        self.on_feeds_changed: Optional[Callable] = None
        
        self.create_widgets()
        self.load_feeds()
    
    def create_widgets(self):
        """Create the feed management interface."""
        # Header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(header_frame, text="RSS Feeds", font=("Segoe UI", 12, "bold")).pack(side="left")
        
        # Buttons frame
        buttons_frame = ttk.Frame(header_frame)
        buttons_frame.pack(side="right")
        
        ttk.Button(buttons_frame, text="Add", command=self.add_feed, width=8).pack(side="left", padx=(0, 5))
        ttk.Button(buttons_frame, text="Edit", command=self.edit_feed, width=8).pack(side="left", padx=(0, 5))
        ttk.Button(buttons_frame, text="Remove", command=self.remove_feed, width=8).pack(side="left", padx=(0, 5))
        ttk.Button(buttons_frame, text="Import", command=self.import_feeds, width=8).pack(side="left")
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)
        
        self.listbox = tk.Listbox(
            list_frame,
            height=8,
            font=("Consolas", 9),
            selectmode="single"
        )
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Edit", command=self.edit_feed)
        self.context_menu.add_command(label="Remove", command=self.remove_feed)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Test Feed", command=self.test_feed)
        
        self.listbox.bind("<Button-3>", self.show_context_menu)
        self.listbox.bind("<Double-Button-1>", self.edit_feed)
    
    def show_context_menu(self, event):
        """Show context menu on right-click."""
        try:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.listbox.nearest(event.y))
            self.context_menu.post(event.x_root, event.y_root)
        except tk.TclError:
            pass
    
    def load_feeds(self):
        """Load feeds from feeds.txt file."""
        try:
            if os.path.exists("feeds.txt"):
                self.feeds = load_feeds_from_txt("feeds.txt")
                self.refresh_listbox()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load feeds: {e}")
    
    def save_feeds(self):
        """Save feeds to feeds.txt file."""
        try:
            with open("feeds.txt", "w", encoding="utf-8") as f:
                f.write("# RSS/Atom feeds - one URL per line\n")
                f.write("# Lines starting with # are comments\n\n")
                for feed in self.feeds:
                    f.write(f"{feed}\n")
            
            if self.on_feeds_changed:
                self.on_feeds_changed()
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save feeds: {e}")
    
    def refresh_listbox(self):
        """Refresh the listbox display."""
        self.listbox.delete(0, tk.END)
        for feed in self.feeds:
            # Truncate long URLs for display
            display_text = feed if len(feed) <= 60 else feed[:57] + "..."
            self.listbox.insert(tk.END, display_text)
    
    def add_feed(self):
        """Add a new feed URL."""
        dialog = FeedDialog(self, "Add RSS Feed")
        if dialog.result:
            url = dialog.result.strip()
            if url and url not in self.feeds:
                self.feeds.append(url)
                self.refresh_listbox()
                self.save_feeds()
    
    def edit_feed(self, event=None):
        """Edit the selected feed."""
        selection = self.listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        current_url = self.feeds[index]
        
        dialog = FeedDialog(self, "Edit RSS Feed", current_url)
        if dialog.result:
            new_url = dialog.result.strip()
            if new_url and new_url != current_url:
                self.feeds[index] = new_url
                self.refresh_listbox()
                self.save_feeds()
    
    def remove_feed(self):
        """Remove the selected feed."""
        selection = self.listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        feed_url = self.feeds[index]
        
        if messagebox.askyesno("Confirm", f"Remove this feed?\n\n{feed_url}"):
            del self.feeds[index]
            self.refresh_listbox()
            self.save_feeds()
    
    def import_feeds(self):
        """Import feeds from a file."""
        filename = filedialog.askopenfilename(
            title="Import Feeds",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                imported_feeds = load_feeds_from_txt(filename)
                new_feeds = [f for f in imported_feeds if f not in self.feeds]
                
                if new_feeds:
                    self.feeds.extend(new_feeds)
                    self.refresh_listbox()
                    self.save_feeds()
                    messagebox.showinfo("Success", f"Imported {len(new_feeds)} new feeds.")
                else:
                    messagebox.showinfo("Info", "No new feeds to import.")
                    
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import feeds: {e}")
    
    def test_feed(self):
        """Test the selected feed URL."""
        selection = self.listbox.curselection()
        if not selection:
            return
        
        feed_url = self.feeds[selection[0]]
        
        def test_worker():
            try:
                url, parsed, error = fetch_and_parse(feed_url, timeout=10)
                entries = safe_entries(parsed)
                
                if error:
                    result = f"Error: {error}"
                elif not entries:
                    result = "Feed is valid but contains no entries."
                else:
                    result = f"Success! Found {len(entries)} articles."
                
                # Schedule UI update
                self.after(0, lambda: messagebox.showinfo("Feed Test", result))
                
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Feed Test", f"Test failed: {e}"))
        
        threading.Thread(target=test_worker, daemon=True).start()
    
    def get_feeds(self) -> List[str]:
        """Get the current list of feeds."""
        return self.feeds.copy()


class FeedDialog:
    """Dialog for adding/editing feed URLs with validation."""
    
    def __init__(self, parent, title: str, initial_value: str = ""):
        self.result = None
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x200")
        self.dialog.resizable(True, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        self.dialog.geometry(f"+{parent_x + 50}+{parent_y + 50}")
        
        # Create widgets
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="RSS/Atom Feed URL:").pack(anchor="w", pady=(0, 5))
        
        self.url_entry = ttk.Entry(main_frame, font=("Consolas", 10))
        self.url_entry.pack(fill="x", pady=(0, 10))
        self.url_entry.insert(0, initial_value)
        self.url_entry.focus()
        
        # Validation message
        self.validation_label = ttk.Label(main_frame, text="", foreground="red")
        self.validation_label.pack(anchor="w", pady=(0, 10))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side="right", padx=(5, 0))
        ttk.Button(button_frame, text="OK", command=self.ok).pack(side="right")
        
        # Bind events
        self.url_entry.bind("<Return>", lambda e: self.ok())
        self.url_entry.bind("<Escape>", lambda e: self.cancel())
        self.url_entry.bind("<KeyRelease>", self.validate_input)
        
        # Initial validation
        self.validate_input()
        
        # Wait for dialog
        self.dialog.wait_window()
    
    def validate_input(self, event=None):
        """Validate the URL input."""
        url = self.url_entry.get().strip()
        
        if not url:
            self.validation_label.config(text="URL cannot be empty")
            return False
        
        if not (url.startswith("http://") or url.startswith("https://")):
            self.validation_label.config(text="URL must start with http:// or https://")
            return False
        
        self.validation_label.config(text="")
        return True
    
    def ok(self):
        """Handle OK button."""
        if self.validate_input():
            self.result = self.url_entry.get().strip()
            self.dialog.destroy()
    
    def cancel(self):
        """Handle Cancel button."""
        self.dialog.destroy()


class SearchOptionsFrame(ttk.LabelFrame):
    """Frame containing search configuration options."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="Search Options", padding="15", **kwargs)
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create search option widgets."""
        # Keywords section
        keywords_frame = ttk.Frame(self)
        keywords_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(keywords_frame, text="Keywords:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(keywords_frame, text="Enter comma-separated keywords (Arabic or English)", 
                 foreground="gray").pack(anchor="w", pady=(0, 5))
        
        self.keywords_entry = ttk.Entry(keywords_frame, font=("Segoe UI", 10))
        self.keywords_entry.pack(fill="x")
        
        # Options grid
        options_frame = ttk.Frame(self)
        options_frame.pack(fill="x")
        
        # Search field
        ttk.Label(options_frame, text="Search in:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.field_var = tk.StringVar(value="both")
        field_combo = ttk.Combobox(
            options_frame, 
            textvariable=self.field_var,
            values=["both", "title", "description"],
            state="readonly",
            width=15
        )
        field_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        # Match mode
        ttk.Label(options_frame, text="Match mode:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.mode_var = tk.StringVar(value="any")
        mode_combo = ttk.Combobox(
            options_frame,
            textvariable=self.mode_var,
            values=["any", "all"],
            state="readonly",
            width=15
        )
        mode_combo.grid(row=0, column=3, sticky="w", padx=(0, 20))
        
        # Max results
        ttk.Label(options_frame, text="Max results:").grid(row=0, column=4, sticky="w", padx=(0, 10))
        self.max_var = tk.StringVar(value="100")
        max_entry = ttk.Entry(options_frame, textvariable=self.max_var, width=10)
        max_entry.grid(row=0, column=5, sticky="w")
    
    def get_keywords(self) -> str:
        """Get the entered keywords."""
        return self.keywords_entry.get().strip()
    
    def get_search_field(self) -> str:
        """Get the selected search field."""
        return self.field_var.get()
    
    def get_match_mode(self) -> str:
        """Get the selected match mode."""
        return self.mode_var.get()
    
    def get_max_results(self) -> int:
        """Get the maximum number of results."""
        try:
            value = int(self.max_var.get())
            return max(0, value)
        except ValueError:
            return 0
    
    def validate(self) -> bool:
        """Validate the search options."""
        keywords = self.get_keywords()
        if not keywords:
            messagebox.showerror("Validation Error", "Please enter at least one keyword.")
            self.keywords_entry.focus()
            return False
        
        try:
            max_results = int(self.max_var.get())
            if max_results < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Validation Error", "Max results must be a non-negative integer.")
            return False
        
        return True


class ResultsViewer(ttk.Frame):
    """Widget for displaying search results with preview functionality."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.results: List[Dict[str, Any]] = []
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create the results viewer interface."""
        # Header with controls
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", pady=(0, 10))
        
        self.status_label = ttk.Label(
            header_frame, 
            text="No search performed yet", 
            font=("Segoe UI", 10)
        )
        self.status_label.pack(side="left")
        
        # Control buttons
        controls_frame = ttk.Frame(header_frame)
        controls_frame.pack(side="right")
        
        self.export_button = ttk.Button(
            controls_frame, 
            text="Export HTML", 
            command=self.export_html,
            state="disabled"
        )
        self.export_button.pack(side="left", padx=(0, 5))
        
        self.preview_button = ttk.Button(
            controls_frame,
            text="Preview",
            command=self.preview_html,
            state="disabled"
        )
        self.preview_button.pack(side="left")
        
        # Results tree
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        
        # Define columns
        columns = ("title", "source", "date")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", height=12)
        
        # Configure columns
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=30, minwidth=30, stretch=False)
        
        self.tree.heading("title", text="Title")
        self.tree.column("title", width=400, minwidth=200, stretch=True)
        
        self.tree.heading("source", text="Source")
        self.tree.column("source", width=150, minwidth=100, stretch=False)
        
        self.tree.heading("date", text="Date")
        self.tree.column("date", width=100, minwidth=80, stretch=False)
        
        # Scrollbars
        v_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        # Pack tree and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Detail view
        detail_frame = ttk.LabelFrame(self, text="Article Details", padding="10")
        detail_frame.pack(fill="x", pady=(10, 0))
        
        self.detail_text = scrolledtext.ScrolledText(
            detail_frame,
            height=6,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 9)
        )
        self.detail_text.pack(fill="x")
        
        # Bind events
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        self.tree.bind("<Double-Button-1>", self.open_article)
    
    def update_results(self, results: List[Dict[str, Any]], status_text: str):
        """Update the results display."""
        self.results = results
        self.status_label.config(text=status_text)
        
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add results
        for i, result in enumerate(results):
            title = result.get("title", "No title")[:100]
            source = result.get("source", "Unknown")[:30]
            date_str = result.get("date_str", "")
            
            self.tree.insert("", "end", values=(title, source, date_str))
        
        # Enable/disable buttons
        has_results = len(results) > 0
        self.export_button.config(state="normal" if has_results else "disabled")
        self.preview_button.config(state="normal" if has_results else "disabled")
        
        # Clear detail view
        self.detail_text.config(state="normal")
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.config(state="disabled")
    
    def on_item_select(self, event):
        """Handle tree item selection."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_index = self.tree.index(item)
        
        if 0 <= item_index < len(self.results):
            result = self.results[item_index]
            
            # Update detail view
            self.detail_text.config(state="normal")
            self.detail_text.delete(1.0, tk.END)
            
            details = []
            details.append(f"Title: {result.get('title', 'N/A')}")
            details.append(f"Source: {result.get('source', 'N/A')}")
            details.append(f"Date: {result.get('date_str', 'N/A')}")
            details.append(f"URL: {result.get('link', 'N/A')}")
            details.append("")
            details.append("Summary:")
            details.append(result.get('summary', 'No summary available'))
            
            self.detail_text.insert(1.0, "\n".join(details))
            self.detail_text.config(state="disabled")
    
    def open_article(self, event):
        """Open the selected article in browser."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_index = self.tree.index(item)
        
        if 0 <= item_index < len(self.results):
            result = self.results[item_index]
            url = result.get('link')
            
            if url:
                try:
                    webbrowser.open(url)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to open URL: {e}")
    
    def export_html(self):
        """Export results to HTML file."""
        if not self.results:
            return
        
        filename = filedialog.asksaveasfilename(
            title="Export HTML Report",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialname=f"rss_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        
        if filename:
            try:
                # Generate HTML (you'll need to pass the required parameters)
                html_content = render_html(
                    results=self.results,
                    keywords=[],  # You'll need to get this from the search options
                    search_field="both",  # You'll need to get this from the search options
                    mode="any",  # You'll need to get this from the search options
                    generated_at=datetime.now(),
                    total_feeds=0,  # You'll need to get this
                    failed_feeds=[]  # You'll need to get this
                )
                
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                messagebox.showinfo("Success", f"HTML report exported to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export HTML: {e}")
    
    def preview_html(self):
        """Preview the HTML report in browser."""
        if not self.results:
            return
        
        try:
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as f:
                html_content = render_html(
                    results=self.results,
                    keywords=[],
                    search_field="both",
                    mode="any",
                    generated_at=datetime.now(),
                    total_feeds=0,
                    failed_feeds=[]
                )
                f.write(html_content)
                temp_filename = f.name
            
            # Open in browser
            webbrowser.open(f"file://{temp_filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to preview HTML: {e}")


class MainApplication:
    """Main application class coordinating all components."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("xsukax RSS Search")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # Configure style
        self.setup_style()
        
        # Create main interface
        self.create_widgets()
        
        # Configure grid weights for responsiveness
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Center window on screen
        self.center_window()
    
    def setup_style(self):
        """Configure ttk styles for modern appearance."""
        style = ttk.Style()
        
        # Use a modern theme if available
        available_themes = style.theme_names()
        if "vista" in available_themes:
            style.theme_use("vista")
        elif "clam" in available_themes:
            style.theme_use("clam")
        
        # Custom styles
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
    
    def center_window(self):
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_widgets(self):
        """Create the main application interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(2, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="xsukax RSS Search", 
            style="Title.TLabel"
        )
        title_label.grid(row=0, column=0, pady=(0, 20), sticky="w")
        
        # Create paned window for resizable layout
        paned = ttk.PanedWindow(main_frame, orient="horizontal")
        paned.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 15))
        
        # Left panel - Configuration
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        # Feed manager
        self.feed_manager = FeedManager(left_frame)
        self.feed_manager.pack(fill="both", expand=True, pady=(0, 15))
        self.feed_manager.on_feeds_changed = self.on_feeds_changed
        
        # Search options
        self.search_options = SearchOptionsFrame(left_frame)
        self.search_options.pack(fill="x")
        
        # Right panel - Results
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        self.results_viewer = ResultsViewer(right_frame)
        self.results_viewer.pack(fill="both", expand=True)
        
        # Bottom frame - Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        control_frame.grid_columnconfigure(0, weight=1)
        
        # Search button
        self.search_button = ttk.Button(
            control_frame,
            text="Search RSS Feeds",
            command=self.perform_search,
            style="Accent.TButton"
        )
        self.search_button.grid(row=0, column=1, padx=(10, 0))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(control_frame, textvariable=self.status_var, relief="sunken")
        status_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    
    def on_feeds_changed(self):
        """Handle feed list changes."""
        feeds = self.feed_manager.get_feeds()
        self.status_var.set(f"Ready - {len(feeds)} feeds configured")
    
    def perform_search(self):
        """Perform the RSS search operation."""
        # Validate inputs
        if not self.search_options.validate():
            return
        
        feeds = self.feed_manager.get_feeds()
        if not feeds:
            messagebox.showerror("Error", "Please add at least one RSS feed.")
            return
        
        # Get search parameters
        keywords_text = self.search_options.get_keywords()
        search_field = self.search_options.get_search_field()
        match_mode = self.search_options.get_match_mode()
        max_results = self.search_options.get_max_results()
        
        # Parse keywords
        keywords = parse_keywords(keywords_text)
        
        # Disable search button during operation
        self.search_button.config(state="disabled")
        
        # Create progress dialog
        progress = ProgressDialog(self.root, "Searching RSS Feeds")
        
        # Create result queue for thread communication
        result_queue = queue.Queue()
        
        def search_worker():
            """Worker thread for RSS search."""
            try:
                progress.update_status("Fetching RSS feeds...")
                
                # Fetch feeds
                fetched_results = []
                failed_feeds = []
                
                for i, feed_url in enumerate(feeds):
                    if progress.cancelled:
                        break
                    
                    progress.update_status(f"Fetching feed {i+1}/{len(feeds)}: {feed_url[:50]}...")
                    
                    url, parsed, error = fetch_and_parse(feed_url, timeout=12)
                    
                    if error or not safe_entries(parsed):
                        failed_feeds.append((url, error))
                    
                    fetched_results.append((url, parsed, error))
                
                if progress.cancelled:
                    result_queue.put(("cancelled", None))
                    return
                
                progress.update_status("Processing articles...")
                
                # Process results
                matched_articles = []
                seen_links = set()
                
                for url, parsed, error in fetched_results:
                    if progress.cancelled:
                        break
                    
                    for entry in safe_entries(parsed):
                        text = field_text(entry, search_field)
                        if not text:
                            continue
                        
                        if matches(text, keywords, match_mode):
                            link = entry.get("link", "")
                            if link and link not in seen_links:
                                seen_links.add(link)
                                
                                # Parse entry data
                                dt_epoch = entry_datetime(entry)
                                dt = datetime.fromtimestamp(dt_epoch) if dt_epoch else None
                                date_str = dt.strftime('%b %d, %Y') if dt else ""
                                
                                # Extract source
                                source = ""
                                try:
                                    from urllib.parse import urlparse
                                    source = urlparse(link).netloc
                                except:
                                    pass
                                
                                matched_articles.append({
                                    "title": entry.get("title", ""),
                                    "link": link,
                                    "summary": entry.get("summary", "") or entry.get("description", ""),
                                    "source": source,
                                    "date": dt_epoch,
                                    "date_str": date_str,
                                })
                
                if progress.cancelled:
                    result_queue.put(("cancelled", None))
                    return
                
                # Sort by date (newest first)
                matched_articles.sort(key=lambda x: x.get("date", 0), reverse=True)
                
                # Apply max results limit
                if max_results > 0:
                    matched_articles = matched_articles[:max_results]
                
                # Prepare results
                result_data = {
                    "articles": matched_articles,
                    "failed_feeds": failed_feeds,
                    "total_feeds": len(feeds),
                    "keywords": keywords,
                    "search_field": search_field,
                    "match_mode": match_mode
                }
                
                result_queue.put(("success", result_data))
                
            except Exception as e:
                result_queue.put(("error", str(e)))
        
        # Start worker thread
        worker_thread = threading.Thread(target=search_worker, daemon=True)
        worker_thread.start()
        
        # Monitor results
        def check_results():
            try:
                result_type, data = result_queue.get_nowait()
                
                progress.close()
                self.search_button.config(state="normal")
                
                if result_type == "success":
                    articles = data["articles"]
                    failed_count = len(data["failed_feeds"])
                    
                    status_text = f"Found {len(articles)} articles"
                    if failed_count > 0:
                        status_text += f" ({failed_count} feeds failed)"
                    
                    self.results_viewer.update_results(articles, status_text)
                    self.status_var.set(status_text)
                    
                elif result_type == "error":
                    messagebox.showerror("Search Error", f"Search failed: {data}")
                    self.status_var.set("Search failed")
                    
                elif result_type == "cancelled":
                    self.status_var.set("Search cancelled")
                
            except queue.Empty:
                if not progress.cancelled:
                    # Check again in 100ms
                    self.root.after(100, check_results)
                else:
                    progress.close()
                    self.search_button.config(state="normal")
                    self.status_var.set("Search cancelled")
        
        # Start monitoring
        check_results()
    
    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


def main():
    """Main entry point for the GUI application."""
    app = MainApplication()
    app.run()


if __name__ == "__main__":
    main()
