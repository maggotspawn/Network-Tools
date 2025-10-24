#!/usr/bin/env python3
"""
Port Scanner with GUI for Windows
A graphical interface for port scanning with result saving
Optimized for Windows 10/11
"""

import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os

class PortScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Port Scanner - Windows Edition")
        self.root.geometry("950x750")
        
        # Windows-specific styling
        try:
            self.root.state('zoomed')  # Maximize on Windows
        except:
            pass
            
        # Set Windows icon if available
        try:
            self.root.iconbitmap('icon.ico')
        except:
            pass
        
        self.scanning = False
        self.scan_thread = None
        self.open_ports = []
        
        # Configure style for Windows
        self.setup_style()
        self.setup_ui()
        
        # Windows-specific bindings
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_style(self):
        """Configure Windows-friendly styling"""
        style = ttk.Style()
        
        # Try to use Windows native theme
        try:
            style.theme_use('vista')  # Windows Vista/7/10/11 theme
        except:
            try:
                style.theme_use('winnative')  # Fallback Windows theme
            except:
                pass
        
        # Custom colors for better Windows integration
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('Header.TLabel', font=('Segoe UI', 10, 'bold'))
        style.configure('TButton', font=('Segoe UI', 9))
        style.configure('Action.TButton', font=('Segoe UI', 10, 'bold'))
        
    def setup_ui(self):
        """Create the user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # Title with icon
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, columnspan=3, pady=(0, 15))
        
        title_label = ttk.Label(title_frame, text="🔍 Port Scanner", 
                               style='Title.TLabel', foreground='#0078D4')
        title_label.pack()
        
        #subtitle = ttk.Label(title_frame, text="Windows Edition", 
                            #font=('Segoe UI', 9, 'italic'))
        #subtitle.pack()
        
        # Target configuration frame
        target_frame = ttk.LabelFrame(main_frame, text=" Target Configuration ", 
                                     padding="15")
        target_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), 
                         pady=(0, 10))
        target_frame.columnconfigure(1, weight=1)
        
        # Target host
        ttk.Label(target_frame, text="Target Host:", 
                 style='Header.TLabel').grid(row=0, column=0, sticky=tk.W, pady=8)
        
        host_inner_frame = ttk.Frame(target_frame)
        host_inner_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=8, padx=(10, 0))
        host_inner_frame.columnconfigure(0, weight=1)
        
        self.host_entry = ttk.Entry(host_inner_frame, font=('Segoe UI', 10))
        self.host_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.host_entry.insert(0, "127.0.0.1")
        
        ttk.Button(host_inner_frame, text="Local", width=8,
                  command=lambda: self.set_host("127.0.0.1")).grid(row=0, column=1, padx=5)
        ttk.Button(host_inner_frame, text="Router", width=8,
                  command=lambda: self.set_host("192.168.1.1")).grid(row=0, column=2)
        
        # Port range frame
        port_frame = ttk.LabelFrame(main_frame, text=" Port Range ", padding="15")
        port_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), 
                       pady=(0, 10))
        port_frame.columnconfigure(1, weight=1)
        port_frame.columnconfigure(3, weight=1)
        
        # Start port
        ttk.Label(port_frame, text="Start Port:", 
                 style='Header.TLabel').grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.start_port_entry = ttk.Entry(port_frame, width=15, font=('Segoe UI', 10))
        self.start_port_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        self.start_port_entry.insert(0, "1")
        
        # End port
        ttk.Label(port_frame, text="End Port:", 
                 style='Header.TLabel').grid(row=0, column=2, sticky=tk.W, padx=(0, 10))
        self.end_port_entry = ttk.Entry(port_frame, width=15, font=('Segoe UI', 10))
        self.end_port_entry.grid(row=0, column=3, sticky=tk.W)
        self.end_port_entry.insert(0, "1024")
        
        # Quick select buttons with Windows styling
        quick_frame = ttk.Frame(port_frame)
        quick_frame.grid(row=1, column=0, columnspan=4, pady=(15, 5))
        
        ttk.Label(quick_frame, text="Quick Select:").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(quick_frame, text="Well-Known (1-1024)", 
                  command=lambda: self.set_port_range(1, 1024)).pack(side=tk.LEFT, padx=3)
        ttk.Button(quick_frame, text="Common Services (1-10000)", 
                  command=lambda: self.set_port_range(1, 10000)).pack(side=tk.LEFT, padx=3)
        ttk.Button(quick_frame, text="Registered (1-49151)", 
                  command=lambda: self.set_port_range(1, 49151)).pack(side=tk.LEFT, padx=3)
        ttk.Button(quick_frame, text="All Ports (1-65535)", 
                  command=lambda: self.set_port_range(1, 65535)).pack(side=tk.LEFT, padx=3)
        
        # Advanced settings frame
        settings_frame = ttk.LabelFrame(main_frame, text=" Advanced Settings ", 
                                       padding="15")
        settings_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), 
                           pady=(0, 10))
        
        # Threads setting
        ttk.Label(settings_frame, text="Concurrent Threads:", 
                 style='Header.TLabel').grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.threads_spinbox = ttk.Spinbox(settings_frame, from_=1, to=500, 
                                          width=10, font=('Segoe UI', 10))
        self.threads_spinbox.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        self.threads_spinbox.set(150)
        
        ttk.Label(settings_frame, text="(Higher = Faster, but more CPU usage)",
                 font=('Segoe UI', 8, 'italic')).grid(row=0, column=2, sticky=tk.W)
        
        # Timeout setting
        ttk.Label(settings_frame, text="Timeout (seconds):", 
                 style='Header.TLabel').grid(row=1, column=0, sticky=tk.W, 
                                            padx=(0, 10), pady=(10, 0))
        self.timeout_spinbox = ttk.Spinbox(settings_frame, from_=0.5, to=10, 
                                          increment=0.5, width=10, 
                                          font=('Segoe UI', 10))
        self.timeout_spinbox.grid(row=1, column=1, sticky=tk.W, 
                                 padx=(0, 20), pady=(10, 0))
        self.timeout_spinbox.set(1)
        
        # Control buttons with Windows styling
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=15)
        
        self.scan_button = ttk.Button(button_frame, text="▶ Start Scan", 
                                      command=self.start_scan, width=18,
                                      style='Action.TButton')
        self.scan_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="⏸ Stop Scan", 
                                      command=self.stop_scan, width=18,
                                      state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="🗑 Clear", 
                  command=self.clear_results, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="💾 Save", 
                  command=self.save_results, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="📋 Copy", 
                  command=self.copy_results, width=15).pack(side=tk.LEFT, padx=5)
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text=" Scan Progress ", 
                                       padding="10")
        progress_frame.grid(row=5, column=0, columnspan=3, 
                           sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.progress_label = ttk.Label(progress_frame, text="Ready to scan",
                                       font=('Segoe UI', 9))
        self.progress_label.grid(row=1, column=0, sticky=tk.W)
        
        # Results area with Windows styling
        results_frame = ttk.LabelFrame(main_frame, text=" Scan Results ", 
                                       padding="10")
        results_frame.grid(row=6, column=0, columnspan=3, 
                          sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        self.results_text = scrolledtext.ScrolledText(results_frame, 
                                                      width=90, height=18,
                                                      wrap=tk.WORD,
                                                      font=('Consolas', 9),
                                                      bg='#F5F5F5')
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar with Windows styling
        status_frame = ttk.Frame(main_frame, relief=tk.SUNKEN, borderwidth=1)
        status_frame.grid(row=7, column=0, columnspan=3, 
                         sticky=(tk.W, tk.E), pady=(5, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(status_frame, text="Ready", 
                                     font=('Segoe UI', 9))
        self.status_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        
        self.stats_label = ttk.Label(status_frame, text="", 
                                     font=('Segoe UI', 9))
        self.stats_label.grid(row=0, column=1, sticky=tk.E, padx=5, pady=2)
        
    def set_host(self, host):
        """Set target host"""
        self.host_entry.delete(0, tk.END)
        self.host_entry.insert(0, host)
        
    def set_port_range(self, start, end):
        """Set port range from quick select buttons"""
        self.start_port_entry.delete(0, tk.END)
        self.start_port_entry.insert(0, str(start))
        self.end_port_entry.delete(0, tk.END)
        self.end_port_entry.insert(0, str(end))
        
    def log(self, message):
        """Add message to results text area"""
        self.results_text.insert(tk.END, message + "\n")
        self.results_text.see(tk.END)
        self.root.update_idletasks()
        
    def update_status(self, message, stats=""):
        """Update status bar"""
        self.status_label.config(text=message)
        self.stats_label.config(text=stats)
        self.root.update_idletasks()
        
    def update_progress_label(self, message):
        """Update progress label"""
        self.progress_label.config(text=message)
        self.root.update_idletasks()
        
    def clear_results(self):
        """Clear the results text area"""
        self.results_text.delete(1.0, tk.END)
        self.open_ports = []
        self.progress['value'] = 0
        self.update_status("Results cleared")
        self.update_progress_label("Ready to scan")
        
    def copy_results(self):
        """Copy results to clipboard"""
        try:
            results = self.results_text.get(1.0, tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(results)
            messagebox.showinfo("Success", "Results copied to clipboard!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {str(e)}")
            
    def validate_inputs(self):
        """Validate user inputs"""
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showerror("Input Error", "Please enter a target host")
            return None
            
        try:
            start_port = int(self.start_port_entry.get())
            end_port = int(self.end_port_entry.get())
            threads = int(self.threads_spinbox.get())
            timeout = float(self.timeout_spinbox.get())
            
            if start_port < 1 or end_port > 65535 or start_port > end_port:
                messagebox.showerror("Input Error", 
                    "Invalid port range!\nMust be between 1-65535 and start ≤ end")
                return None
                
            if threads < 1 or threads > 500:
                messagebox.showerror("Input Error", "Threads must be between 1-500")
                return None
                
            if timeout < 0.5 or timeout > 10:
                messagebox.showerror("Input Error", "Timeout must be between 0.5-10 seconds")
                return None
                
            return host, start_port, end_port, threads, timeout
            
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numbers")
            return None
            
    def scan_port(self, host, port, timeout=1):
        """Scan a single port"""
        if not self.scanning:
            return None
            
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                return port
            return None
        except:
            return None
            
    def get_service_name(self, port):
        """Get service name for a port"""
        try:
            return socket.getservbyport(port)
        except:
            return "unknown"
            
    def perform_scan(self, host, start_port, end_port, max_workers, timeout):
        """Perform the actual port scan"""
        self.open_ports = []
        start_time = datetime.now()
        
        self.log("=" * 70)
        self.log(f"  PORT SCANNER - SCAN REPORT")
        self.log("=" * 70)
        self.log(f"Target Host:    {host}")
        self.log(f"Port Range:     {start_port} - {end_port}")
        self.log(f"Scan Started:   {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Threads:        {max_workers}")
        self.log(f"Timeout:        {timeout}s")
        self.log("=" * 70)
        self.log("")
        
        try:
            target_ip = socket.gethostbyname(host)
            self.log(f"✓ Resolved to IP: {target_ip}")
            self.log("")
            
            total_ports = end_port - start_port + 1
            completed = 0
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_port = {
                    executor.submit(self.scan_port, target_ip, port, timeout): port
                    for port in range(start_port, end_port + 1)
                }
                
                for future in as_completed(future_to_port):
                    if not self.scanning:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                        
                    completed += 1
                    result = future.result()
                    
                    if result:
                        service = self.get_service_name(result)
                        self.log(f"  [OPEN] Port {result:5d}  →  {service}")
                        self.open_ports.append((result, service))
                    
                    # Update progress
                    progress = (completed / total_ports) * 100
                    self.progress['value'] = progress
                    
                    if completed % 100 == 0 or completed == total_ports:
                        self.update_progress_label(
                            f"Scanned {completed:,} / {total_ports:,} ports  |  "
                            f"Open: {len(self.open_ports)}")
                        self.update_status(
                            f"Scanning in progress...",
                            f"{completed:,}/{total_ports:,} ports")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if self.scanning:
                self.log("")
                self.log("=" * 70)
                self.log(f"  SCAN COMPLETED")
                self.log("=" * 70)
                self.log(f"End Time:       {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.log(f"Duration:       {duration:.2f} seconds")
                self.log(f"Ports Scanned:  {completed:,}")
                self.log(f"Open Ports:     {len(self.open_ports)}")
                self.log(f"Scan Rate:      {completed/duration:.0f} ports/sec")
                self.log("=" * 70)
                
                if self.open_ports:
                    self.log("")
                    self.log("  OPEN PORTS SUMMARY:")
                    self.log("  " + "-" * 66)
                    self.log(f"  {'Port':<10} {'Service':<20} {'Description'}")
                    self.log("  " + "-" * 66)
                    for port, service in sorted(self.open_ports):
                        self.log(f"  {port:<10} {service:<20}")
                else:
                    self.log("")
                    self.log("  No open ports found in the specified range.")
                    
                self.update_status(
                    f"✓ Scan complete in {duration:.1f}s",
                    f"{len(self.open_ports)} open ports")
                self.update_progress_label(
                    f"Completed: {len(self.open_ports)} open ports found")
            else:
                self.log("")
                self.log("⚠ Scan stopped by user")
                self.update_status("Scan stopped by user")
                self.update_progress_label("Scan interrupted")
                
        except socket.gaierror:
            self.log("")
            self.log(f"✗ ERROR: Cannot resolve hostname '{host}'")
            self.update_status("Error: Cannot resolve hostname")
            messagebox.showerror("Network Error", 
                f"Cannot resolve hostname: {host}\n\nPlease check the address and try again.")
        except Exception as e:
            self.log("")
            self.log(f"✗ ERROR: {str(e)}")
            self.update_status(f"Error occurred")
            messagebox.showerror("Scan Error", f"An error occurred:\n\n{str(e)}")
        finally:
            self.scanning = False
            self.scan_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
    def start_scan(self):
        """Start the port scan in a separate thread"""
        inputs = self.validate_inputs()
        if not inputs:
            return
            
        host, start_port, end_port, threads, timeout = inputs
        
        # Confirm large scans
        total_ports = end_port - start_port + 1
        if total_ports > 10000:
            response = messagebox.askyesno("Large Scan Warning",
                f"You are about to scan {total_ports:,} ports.\n"
                f"This may take several minutes.\n\n"
                f"Do you want to continue?")
            if not response:
                return
        
        self.scanning = True
        self.scan_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.clear_results()
        self.update_status("Initializing scan...")
        self.update_progress_label("Starting scan...")
        
        self.scan_thread = threading.Thread(
            target=self.perform_scan,
            args=(host, start_port, end_port, threads, timeout),
            daemon=True
        )
        self.scan_thread.start()
        
    def stop_scan(self):
        """Stop the current scan"""
        if messagebox.askyesno("Stop Scan", "Are you sure you want to stop the scan?"):
            self.scanning = False
            self.update_status("Stopping scan...")
        
    def save_results(self):
        """Save scan results to a file"""
        if not self.results_text.get(1.0, tk.END).strip():
            messagebox.showwarning("No Results", "No results to save")
            return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        host = self.host_entry.get().strip().replace('.', '_').replace(':', '_')
        default_name = f"portscan_{host}_{timestamp}.txt"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[
                ("Text files", "*.txt"),
                ("Log files", "*.log"),
                ("All files", "*.*")
            ],
            title="Save Scan Results"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.results_text.get(1.0, tk.END))
                messagebox.showinfo("Success", 
                    f"Results saved successfully!\n\n{filename}")
                self.update_status(f"Results saved to {os.path.basename(filename)}")
                
                # Ask to open file
                if messagebox.askyesno("Open File", "Do you want to open the file now?"):
                    os.startfile(filename)  # Windows-specific
            except Exception as e:
                messagebox.showerror("Save Error", 
                    f"Failed to save file:\n\n{str(e)}")
                
    def on_closing(self):
        """Handle window closing"""
        if self.scanning:
            if messagebox.askokcancel("Quit", 
                "A scan is in progress. Do you want to stop it and quit?"):
                self.scanning = False
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    root = tk.Tk()
    
    # Windows-specific configurations
    try:
        # Enable DPI awareness for Windows 10/11
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    app = PortScannerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()