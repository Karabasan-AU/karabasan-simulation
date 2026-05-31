# UI Module

## Structure

```markdown

ui/
├── main.py                  # Entry point only — creates QApplication, launches MainWindow
├── main_window.py           # MainWindow class — layout assembly, wires everything together
├── components/
│   ├── __init__.py
│   ├── spectrum_panel.py    # Spectrum plot + waterfall heatmap (left panel)
│   ├── df_radar.py          # Compass/DF radar widget
│   ├── target_table.py      # ED target table
│   ├── et_panel.py          # ET attack buttons
│   └── log_console.py       # Log console widget + update_sigint_log logic
└── listeners/
    ├── __init__.py
    └── zmq_listener.py      # QThread listener — replaces RedisListener

```

Reasoning for key decisions:

* components/ each map to one visual panel — easy to find, easy to replace
* log_console.py owns update_sigint_log since it's purely a display concern
* listeners/ is its own package — swapping transports later touches only this folder
* main_window.py is the only file that imports from both components/ and listeners/ — it's the wiring layer
* main.py stays tiny: just QApplication + MainWindow + sys.exit