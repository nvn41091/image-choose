from PySide6.QtGui import QColor, QPalette


def apply_theme(app, dark):
    app.setStyle('Fusion')
    if dark:
        window, surface, text, muted, border, accent, selection, error = (
            '#191f1e', '#232b29', '#f2f5f3', '#b4c2bc', '#45534d', '#8cc7b0', '#305d50', '#ffb8ab')
        primary_text, hover = '#12271f', '#a7d8c5'
    else:
        window, surface, text, muted, border, accent, selection, error = (
            '#f4f6f4', '#ffffff', '#202c28', '#52635b', '#c7d2cc', '#28624e', '#28624e', '#a13125')
        primary_text, hover = '#ffffff', '#34765e'
    palette = QPalette()
    for role, color in {
        'Window': window, 'Base': surface, 'AlternateBase': window, 'Text': text, 'WindowText': text,
        'Button': surface, 'ButtonText': text, 'Mid': border, 'Highlight': selection,
        'Dark': border, 'Shadow': muted,
        'HighlightedText': '#ffffff', 'Link': accent, 'ToolTipBase': surface, 'ToolTipText': text,
        'PlaceholderText': muted,
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ('Text', 'WindowText', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(muted))
    app.setPalette(palette)
    app.setStyleSheet(f'''
        QWidget {{ color: {text}; }}
        QFrame#panel, QFrame#toolbar {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
        QLabel#sectionTitle {{ font-size: 16px; font-weight: 700; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#inlineError {{ color: {error}; }}
        QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 6px 10px; min-height: 19px; }}
        QPushButton:hover {{ border-color: {accent}; }}
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QListView:focus {{ border: 2px solid {accent}; }}
        QPushButton:checked {{ border-color: {accent}; color: {accent}; font-weight: 700; }}
        QPushButton#primary {{ background: {accent}; color: {primary_text}; border-color: {accent}; font-weight: 700; padding: 9px 15px; }}
        QPushButton#primary:hover {{ background: {hover}; }}
        QPushButton#primary:focus {{ border: 2px solid {text}; }}
        QPushButton:disabled, QPushButton#primary:disabled {{ background: {window}; color: {muted}; border-color: {border}; }}
        QLineEdit, QPlainTextEdit, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 5px; }}
        QListView {{ background: {window}; border: 1px solid {border}; border-radius: 6px; }}
        QTabWidget::pane {{ border: 0; }}
        QTabBar::tab {{ background: {window}; color: {muted}; padding: 8px 16px; border-bottom: 2px solid transparent; }}
        QTabBar::tab:selected {{ color: {text}; border-bottom-color: {accent}; font-weight: 700; }}
        QTabBar::tab:focus {{ border: 2px solid {accent}; }}
        QProgressBar {{ border: 1px solid {border}; border-radius: 4px; text-align: center; }}
        QProgressBar::chunk {{ background: {selection}; }}
    ''')
