import tkinter as tk
from tkinter import ttk, scrolledtext
from scapy.all import sniff, IP, TCP, UDP, ARP, Ether
import threading
import socket
from datetime import datetime

class NetworkMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Network Traffic Monitor")
        self.root.geometry("1200x700")
        self.root.configure(bg='#2b2b2b')
        
        self.monitoring = False
        self.packet_count = 0
        
        # Top control panel
        control_frame = tk.Frame(root, bg='#2b2b2b', pady=10)
        control_frame.pack(fill=tk.X, padx=10)
        
        self.start_btn = tk.Button(control_frame, text="Start Monitoring", 
                                   command=self.start_monitoring,
                                   bg='#4CAF50', fg='white', 
                                   font=('Arial', 10, 'bold'),
                                   padx=20, pady=5)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(control_frame, text="Stop Monitoring",
                                  command=self.stop_monitoring,
                                  bg='#f44336', fg='white',
                                  font=('Arial', 10, 'bold'),
                                  padx=20, pady=5, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = tk.Button(control_frame, text="Clear Log",
                                   command=self.clear_log,
                                   bg='#FF9800', fg='white',
                                   font=('Arial', 10, 'bold'),
                                   padx=20, pady=5)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Statistics frame
        stats_frame = tk.Frame(root, bg='#363636', pady=5)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.packet_label = tk.Label(stats_frame, text="Packets Captured: 0",
                                     bg='#363636', fg='#4CAF50',
                                     font=('Arial', 10, 'bold'))
        self.packet_label.pack(side=tk.LEFT, padx=10)
        
        self.status_label = tk.Label(stats_frame, text="Status: Idle",
                                     bg='#363636', fg='#FFC107',
                                     font=('Arial', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Notebook for different views
        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Detailed log tab
        log_frame = tk.Frame(notebook, bg='#2b2b2b')
        notebook.add(log_frame, text="Detailed Log")
        
        self.log_text = scrolledtext.ScrolledText(log_frame, 
                                                  wrap=tk.WORD,
                                                  bg='#1e1e1e',
                                                  fg='#00ff00',
                                                  font=('Consolas', 9),
                                                  insertbackground='white')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Packet table tab
        table_frame = tk.Frame(notebook, bg='#2b2b2b')
        notebook.add(table_frame, text="Packet Table")
        
        # Create treeview for packet table
        columns = ('Time', 'Protocol', 'Source IP', 'Dest IP', 'Src Port', 'Dst Port', 'Length')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=25)
        
        # Configure columns
        self.tree.heading('Time', text='Time')
        self.tree.heading('Protocol', text='Protocol')
        self.tree.heading('Source IP', text='Source IP')
        self.tree.heading('Dest IP', text='Destination IP')
        self.tree.heading('Src Port', text='Src Port')
        self.tree.heading('Dst Port', text='Dst Port')
        self.tree.heading('Length', text='Length')
        
        self.tree.column('Time', width=100)
        self.tree.column('Protocol', width=80)
        self.tree.column('Source IP', width=150)
        self.tree.column('Dest IP', width=150)
        self.tree.column('Src Port', width=80)
        self.tree.column('Dst Port', width=80)
        self.tree.column('Length', width=80)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Get local IP
        self.local_ip = self.get_local_ip()
        self.log_text.insert(tk.END, f"Local IP Address: {self.local_ip}\n")
        self.log_text.insert(tk.END, "="*80 + "\n\n")
        
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "Unable to determine"
    
    def packet_callback(self, packet):
        if not self.monitoring:
            return
        
        self.packet_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Extract packet information
        protocol = "Unknown"
        src_ip = "N/A"
        dst_ip = "N/A"
        src_port = "N/A"
        dst_port = "N/A"
        src_mac = "N/A"
        dst_mac = "N/A"
        length = len(packet)
        
        # Get MAC addresses
        if packet.haslayer(Ether):
            src_mac = packet[Ether].src
            dst_mac = packet[Ether].dst
        
        # Get IP information
        if packet.haslayer(IP):
            src_ip = packet[IP].src
            dst_ip = packet[IP].dst
            
            if packet.haslayer(TCP):
                protocol = "TCP"
                src_port = packet[TCP].sport
                dst_port = packet[TCP].dport
            elif packet.haslayer(UDP):
                protocol = "UDP"
                src_port = packet[UDP].sport
                dst_port = packet[UDP].dport
            else:
                protocol = "IP"
        
        elif packet.haslayer(ARP):
            protocol = "ARP"
            src_ip = packet[ARP].psrc
            dst_ip = packet[ARP].pdst
        
        # Update GUI
        self.root.after(0, self.update_gui, timestamp, protocol, src_ip, dst_ip, 
                       src_port, dst_port, src_mac, dst_mac, length)
    
    def update_gui(self, timestamp, protocol, src_ip, dst_ip, src_port, dst_port, 
                   src_mac, dst_mac, length):
        # Update packet count
        self.packet_label.config(text=f"Packets Captured: {self.packet_count}")
        
        # Add to detailed log
        log_entry = f"[{timestamp}] {protocol}\n"
        log_entry += f"  Source: {src_ip}:{src_port} (MAC: {src_mac})\n"
        log_entry += f"  Destination: {dst_ip}:{dst_port} (MAC: {dst_mac})\n"
        log_entry += f"  Length: {length} bytes\n"
        log_entry += "-" * 80 + "\n"
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        # Add to table
        self.tree.insert('', 0, values=(timestamp, protocol, src_ip, dst_ip, 
                                        src_port, dst_port, length))
        
        # Limit table to 1000 entries
        if len(self.tree.get_children()) > 1000:
            self.tree.delete(self.tree.get_children()[-1])
    
    def start_monitoring(self):
        self.monitoring = True
        self.packet_count = 0
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Monitoring...", fg='#4CAF50')
        
        self.log_text.insert(tk.END, f"\n{'='*80}\n")
        self.log_text.insert(tk.END, f"Started monitoring at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_text.insert(tk.END, f"{'='*80}\n\n")
        
        # Start sniffing in a separate thread
        self.sniffer_thread = threading.Thread(target=self.start_sniffing, daemon=True)
        self.sniffer_thread.start()
    
    def start_sniffing(self):
        try:
            # Sniff packets (requires admin/root privileges)
            sniff(prn=self.packet_callback, store=False, stop_filter=lambda x: not self.monitoring)
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
    
    def show_error(self, error):
        self.log_text.insert(tk.END, f"\nERROR: {error}\n")
        self.log_text.insert(tk.END, "NOTE: This application requires administrator privileges to capture packets.\n")
        self.log_text.insert(tk.END, "Please run this script as administrator/root.\n\n")
        self.stop_monitoring()
    
    def stop_monitoring(self):
        self.monitoring = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Stopped", fg='#f44336')
        
        self.log_text.insert(tk.END, f"\n{'='*80}\n")
        self.log_text.insert(tk.END, f"Stopped monitoring at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_text.insert(tk.END, f"Total packets captured: {self.packet_count}\n")
        self.log_text.insert(tk.END, f"{'='*80}\n\n")
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Local IP Address: {self.local_ip}\n")
        self.log_text.insert(tk.END, "="*80 + "\n\n")
        
        # Clear table
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.packet_count = 0
        self.packet_label.config(text="Packets Captured: 0")

if __name__ == "__main__":
    root = tk.Tk()
    app = NetworkMonitor(root)
    root.mainloop()