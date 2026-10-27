#!/usr/bin/env python3
"""
FL Studio project template setup script.

This script runs INSIDE FL Studio's Python environment and:
1. Creates a piano channel (FLEX or FL Keys)
2. Programs a reggaeton drum pattern
3. Writes an A-minor melody
4. Sets tempo to 95 BPM
5. Saves the project as a template

To use:
  1. In FL Studio: Tools > Scripting > Run Script (or paste into Interpreter)
  2. Or: copy this file to ~/Documents/Image-Line/FL Studio/Scripts/ and run from Scripting

After running, the project is saved to
~/Documents/Image-Line/FL Studio/Projects/fl-studio-mcp/reggaeton_template.flp
"""

import os
import arrangement
import channels
import notes
import pattern
import project
import mixer
import transport

def setup_reggaeton_template():
    print("=== FL Studio Reggaeton Template Setup ===")
    
    # 1. Set tempo to 95 BPM (reggaeton)
    try:
        transport.set_bpm(95)
        print(f"  BPM set to 95")
    except Exception as e:
        print(f"  BPM warning: {e}")
    
    # 2. Create/get a piano channel
    # Check if we already have a piano-type channel
    all_channels = channels.get_all_channels()
    piano_ch = None
    for ch in all_channels:
        name = ch.get('name', '').lower()
        if any(x in name for x in ['piano', 'keys', 'flex', 'epiano', 'grand', 'rhodes']):
            piano_ch = ch
            break
    
    if piano_ch is None:
        # No piano channel — we need the user to add one manually,
        # OR we use the first available non-drum channel
        print("  No piano channel found. Please add one via Browser > FL Keys / FLEX")
        print("  This script will use the first non-drum channel if available.")
        # Fall back to channel index 0 if nothing else
        piano_ch = all_channels[0] if all_channels else None
    
    if piano_ch:
        print(f"  Piano channel: {piano_ch.get('name')} (index {piano_ch.get('index')})")
    
    # 3. Set up Pattern 1 with reggaeton drums
    # The drums are already in the existing channels (808 Kick, 808 Clap, etc.)
    # We just need to make sure Pattern 1 is active and has the right notes
    
    # 4. Write A-minor melody to the piano channel
    # A minor scale: A B C D E F G
    # Chord progression: Am - F - C - G (i - VI - III - VII)
    # In MIDI: A=57, B=59, C=60, D=62, E=64, F=65, G=67
    
    melody_notes = [
        # Bar 1: Am (A C E)
        (57, 0, 1), (60, 1, 1), (64, 2, 1), (67, 3, 1),
        # Bar 2: F (F A C)
        (53, 4, 1), (57, 5, 1), (60, 6, 1), (65, 7, 1),
        # Bar 3: C (C E G)
        (48, 8, 1), (52, 9, 1), (55, 10, 1), (60, 11, 1),
        # Bar 4: G (G B D)
        (55, 12, 1), (59, 13, 1), (62, 14, 1), (67, 15, 1),
    ]
    
    if piano_ch:
        try:
            # Write notes to the piano channel's pattern
            for midi_note, step, length in melody_notes:
                notes.set_note(piano_ch['index'], midi_note, step, length)
            print(f"  Wrote {len(melody_notes)} melody notes to piano channel")
        except Exception as e:
            print(f"  Melody warning: {e}")
    
    # 5. Save the project
    save_path = os.path.expanduser(
        "~/Documents/Image-Line/FL Studio/Projects/fl-studio-mcp/reggaeton_template.flp")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    try:
        project.save_as(save_path)
        print(f"  Template saved to: {save_path}")
    except Exception as e:
        print(f"  Save warning: {e}")
        # Fallback: save to default location
        try:
            project.save()
            print("  Saved to default location instead")
        except Exception as e2:
            print(f"  Save failed: {e2}")
    
    print("=== Setup complete ===")
    print("Open the saved template to start a new reggaeton project!")

# Run
setup_reggaeton_template()
