import tkinter as tk
from tkinter import ttk, messagebox
import re

version = 1
class LoginUI:
    def __init__(self, root, login_callback, register_callback):
        self.root = root
        self.login_callback = login_callback
        self.register_callback = register_callback
        
        # Setup root window
        self.root.title("Login System")
        self.root.geometry("500x800")
        self.root.resizable(True, True)
        
        # Setup styles
        self.style = ttk.Style()
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0', font=('Arial', 12))
        self.style.configure('TEntry', font=('Arial', 12))
        self.style.configure('TButton', font=('Arial', 12))
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create and setup all GUI widgets."""
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            self.main_frame,
            text="User Authentication System",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(pady=20)
        
        self._create_login_frame()
        self._create_register_frame()
    
    def _create_login_frame(self):
        self.login_frame = ttk.LabelFrame(self.main_frame, text="Login", padding="10")
        self.login_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(self.login_frame, text="Username:").pack(fill=tk.X, pady=5)
        self.login_username = ttk.Entry(self.login_frame)
        self.login_username.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.login_frame, text="Password:").pack(fill=tk.X, pady=5)
        self.login_password = ttk.Entry(self.login_frame, show="*")
        self.login_password.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            self.login_frame,
            text="Login",
            command=self._handle_login
        ).pack(fill=tk.X, pady=10)
    
    def _create_register_frame(self):
        self.register_frame = ttk.LabelFrame(self.main_frame, text="Register", padding="10")
        self.register_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(self.register_frame, text="Username:").pack(fill=tk.X, pady=5)
        self.register_username = ttk.Entry(self.register_frame)
        self.register_username.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.register_frame, text="Password:").pack(fill=tk.X, pady=5)
        self.register_password = ttk.Entry(self.register_frame, show="*")
        self.register_password.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.register_frame, text="Confirm Password:").pack(fill=tk.X, pady=5)
        self.register_confirm = ttk.Entry(self.register_frame, show="*")
        self.register_confirm.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.register_frame, text="Email:").pack(fill=tk.X, pady=5)
        self.register_email = ttk.Entry(self.register_frame)
        self.register_email.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            self.register_frame,
            text="Register",
            command=self._handle_register
        ).pack(fill=tk.X, pady=10)
    
    def _validate_email(self, email):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def _handle_login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get()
        
        if not username or not password:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        self.login_callback(username, password)
    
    def _handle_register(self):
        username = self.register_username.get().strip()
        password = self.register_password.get()
        confirm = self.register_confirm.get()
        email = self.register_email.get().strip()
        
        if not all([username, password, confirm, email]):
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        if password != confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return
        
        if not self._validate_email(email):
            messagebox.showerror("Error", "Invalid email format")
            return
        
        if len(password) < 8:
            messagebox.showerror("Error", "Password must be at least 8 characters")
            return
        
        self.register_callback(username, password, email)