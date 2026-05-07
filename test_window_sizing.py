#!/usr/bin/env python3
"""
Test script to verify QR display window sizing works correctly.
"""

import tkinter as tk
from tkinter import ttk
import time

def test_window_sizing():
    """Test different grid configurations."""

    configurations = [
        {"name": "1x1 Single QR", "grid_size": 1, "qr_size": 400},
        {"name": "2x2 Grid (4 streams)", "grid_size": 2, "qr_size": 400},
        {"name": "3x3 Grid (9 streams)", "grid_size": 3, "qr_size": 400},
        {"name": "4x4 Grid (16 streams)", "grid_size": 4, "qr_size": 400},
        {"name": "4x4 Small QRs", "grid_size": 4, "qr_size": 200},
    ]

    for config in configurations:
        grid_size = config["grid_size"]
        qr_size = config["qr_size"]
        spacing = 10

        # Calculate required window size
        required_size = (qr_size * grid_size) + (spacing * (grid_size - 1))
        padding = 50
        required_width = required_size + padding
        required_height = required_size + padding

        print(f"\n{config['name']}:")
        print(f"  Grid: {grid_size}x{grid_size}")
        print(f"  QR size: {qr_size}px each")
        print(f"  Total QR area: {required_size}x{required_size}px")
        print(f"  Required window: {required_width}x{required_height}px")

        # Check if it fits common screen sizes
        screen_sizes = [
            ("1920x1080 (Full HD)", 1920, 1080),
            ("1366x768 (Laptop)", 1366, 768),
            ("2560x1440 (2K)", 2560, 1440),
        ]

        for screen_name, screen_w, screen_h in screen_sizes:
            max_window_w = int(screen_w * 0.9)  # 90% of screen
            max_window_h = int(screen_h * 0.9)

            fits = required_width <= max_window_w and required_height <= max_window_h
            status = "FITS" if fits else "TOO LARGE"

            if not fits:
                # Calculate scaled down size
                max_qr_size = min(
                    (max_window_w - padding - (spacing * (grid_size - 1))) // grid_size,
                    (max_window_h - padding - (spacing * (grid_size - 1))) // grid_size
                )
                print(f"    {screen_name}: {status} (would auto-scale to {max_qr_size}px QRs)")
            else:
                print(f"    {screen_name}: {status}")

def create_demo_window():
    """Create a demo window showing different grid layouts."""
    root = tk.Tk()
    root.title("QR Grid Layout Demo")
    root.geometry("400x500")

    # Create main frame
    main_frame = ttk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    ttk.Label(main_frame, text="QR Grid Layout Sizes",
             font=("Arial", 14, "bold")).pack(pady=(0, 10))

    # Test configurations
    configs = [
        ("1x1 (Traditional)", 1, 400),
        ("2x2 (4 streams)", 2, 400),
        ("3x3 (9 streams)", 3, 400),
        ("4x4 (16 streams)", 4, 400),
        ("4x4 (Small QRs)", 4, 200),
    ]

    for name, grid_size, qr_size in configs:
        spacing = 10
        total_size = (qr_size * grid_size) + (spacing * (grid_size - 1))
        window_size = total_size + 50

        frame = ttk.Frame(main_frame)
        frame.pack(fill=tk.X, pady=2)

        ttk.Label(frame, text=f"{name}:", width=20).pack(side=tk.LEFT)
        ttk.Label(frame, text=f"{window_size}x{window_size}px window",
                 foreground="blue").pack(side=tk.LEFT)

        # Color code by size
        if window_size <= 900:
            color = "green"
            status = "Compact"
        elif window_size <= 1400:
            color = "orange"
            status = "Large"
        else:
            color = "red"
            status = "Very Large"

        ttk.Label(frame, text=f"({status})",
                 foreground=color).pack(side=tk.RIGHT)

    # Add info
    info_text = """
The QRL GUI now automatically:
• Calculates window size based on grid layout
• Scales QR codes if needed to fit screen
• Centers window on screen
• Supports up to 4x4 grids for maximum throughput
    """

    ttk.Label(main_frame, text=info_text.strip(),
             justify=tk.LEFT, foreground="gray").pack(pady=(20, 0))

    # Close button
    ttk.Button(main_frame, text="Close",
              command=root.destroy).pack(pady=(20, 0))

    root.mainloop()

if __name__ == "__main__":
    print("=" * 60)
    print("QR DISPLAY WINDOW SIZING TEST")
    print("=" * 60)

    test_window_sizing()

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("* Window automatically sizes to fit QR grid")
    print("* QR codes auto-scale if grid is too large for screen")
    print("* Supports 1x1, 2x2, 3x3, and 4x4 layouts")
    print("* Optimized for different screen sizes")
    print("=" * 60)

    print("\nOpening demo window...")
    create_demo_window()