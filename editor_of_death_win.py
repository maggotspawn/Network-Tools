#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# #31.py — Editor of Death (PyQt6)
# Update: Fixed syntax check to skip comments, fixed move tab shortcuts, draggable tabs, PDF save, improved line highlight contrast, horizontal resize
# - All commands now operate on the *clicked* tab.
# - Tracks the last clicked/selected editor across panes.
# - Right-clicking an editor sets it as the command target.
# - Switching tabs sets the target.
# - Compare uses the clicked tab as base (opposite pane becomes the compare target).
# - Keeps #24 features (char-level, whitespace-sensitive compare, reliable save prompts, splash).

import sys, os, time, hashlib, re, difflib, subprocess, platform, tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QRect, QSize, QSettings, QPoint, QMimeData
from PyQt6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QKeySequence,
    QPainter, QTextCursor, QTextFormat, QPixmap, QTextCharFormat,
    QSyntaxHighlighter, QTextDocument, QTextOption, QDrag
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPlainTextEdit, QFileDialog, QMessageBox,
    QTabWidget, QSplitter, QInputDialog, QFontDialog,
    QStatusBar, QSplashScreen, QMenu, QTextEdit, QScrollBar, QTabBar,
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QListWidget, QListWidgetItem, QLabel
)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter


# ---------------- Splash (same behavior as stable earlier) ----------------
def create_splash():
    try:
        splash_path = Path(__file__).parent / "splash.png"
        if splash_path.exists():
            pixmap = QPixmap(str(splash_path))
            pixmap = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = QPixmap(800, 600); pixmap.fill(QColor(20, 20, 20))
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Courier New", 38, QFont.Weight.Bold))
        r = pixmap.rect(); r.setTop(40); r.setBottom(120)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "Editor of Death")
        painter.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        r2 = pixmap.rect(); r2.setTop(pixmap.height()-100); r2.setBottom(pixmap.height()-50)
        painter.drawText(r2, Qt.AlignmentFlag.AlignCenter, "Death's Head Software")
        painter.end()
        splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        messages = ["Loading Editor of Death...", "Bootstrapping syntax engines...", "Priming highlighters...", "Ready to slay typos."]
        return splash, messages
    except Exception:
        return None, []


# ---------------- Line number gutter ----------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        # This widget is a fixed ruler - it never scrolls
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        
    def sizeHint(self): 
        return QSize(self.editor.line_number_area_width(), 0)
    
    def paintEvent(self, event): 
        self.editor.line_number_area_paint_event(event)


# ---------------- Highlighters (minimal set kept) ----------------
class BaseHighlighter(QSyntaxHighlighter):
    def __init__(self, doc: QTextDocument, dark: bool = False):
        super().__init__(doc)
        self.dark = dark
        
        # Set colors based on theme
        if dark:
            # Dark mode colors - brighter for visibility on dark background
            self.c_string = QColor(206, 145, 120)      # Light salmon
            self.c_number = QColor(181, 206, 168)      # Light green
            self.c_comment = QColor(106, 153, 85)      # Medium green
            self.c_type = QColor(78, 201, 176)         # Cyan
            self.c_kw = QColor(86, 156, 214)           # Light blue
            self.c_func = QColor(220, 220, 170)        # Light yellow
            self.c_deco = QColor(197, 134, 192)        # Light pink
            self.c_regex = QColor(255, 198, 109)       # Orange
        else:
            # Light mode colors - darker for visibility on light background
            self.c_string = QColor(163, 21, 21)        # Dark red
            self.c_number = QColor(9, 134, 88)         # Dark green
            self.c_comment = QColor(0, 128, 0)         # Green
            self.c_type = QColor(0, 128, 128)          # Teal
            self.c_kw = QColor(0, 0, 255)              # Blue
            self.c_func = QColor(121, 94, 38)          # Dark yellow/brown
            self.c_deco = QColor(128, 0, 128)          # Purple
            self.c_regex = QColor(255, 140, 0)         # Dark orange
            
    def fmt(self, color: QColor, bold=False, italic=False):
        f = QTextCharFormat(); f.setForeground(color)
        if bold: f.setFontWeight(QFont.Weight.Bold)
        if italic: f.setFontItalic(True)
        return f
    def highlightBlock(self, text: str) -> None:
        return  # neutral default

class PythonHighlighter(BaseHighlighter):
    STATE_NONE = 0; STATE_TRIPLE_S = 1; STATE_TRIPLE_D = 2
    kw = set("""
        False await else import pass None break except in raise True class finally is return and continue
        for lambda try as def from nonlocal while assert del global not with async elif if or yield
    """.split())
    builtins = set("""
        abs dict help min setattr all dir hex next slice any divmod id object sorted ascii enumerate input
        oct staticmethod bin eval int open str bool exec isinstance ord sum bytearray filter issubclass pow
        super bytes float iter print tuple callable format len property type chr frozenset list range vars
        classmethod getattr locals repr zip compile globals map reversed __import__ complex hasattr max round
    """.split())
    def highlightBlock(self, text: str):
        st = self.previousBlockState(); st = st if st != -1 else self.STATE_NONE
        n = len(text); i = 0
        if st in (self.STATE_TRIPLE_S, self.STATE_TRIPLE_D):
            endq = "'''" if st == self.STATE_TRIPLE_S else '"""'
            end_idx = text.find(endq, 0)
            if end_idx == -1:
                self.setFormat(0, n, self.fmt(self.c_string)); self.setCurrentBlockState(st); return
            self.setFormat(0, end_idx+3, self.fmt(self.c_string))
            i = end_idx+3; st = self.STATE_NONE
        for m in re.finditer(r"@[A-Za-z_][A-Za-z0-9_\.]*", text):
            self.setFormat(m.start(), m.end()-m.start(), self.fmt(self.c_deco, bold=True))
        cm = re.search(r"#[^\n]*", text[i:]); comment_start = i + cm.start() if cm else -1
        pat = re.compile(r"(?P<p>[fF]?)((?P<ts>'''|\"\"\")|(?P<s>')|(?P<d>\"))")
        idx = i
        while idx < n:
            m = pat.search(text, idx)
            if not m: break
            start = m.start(); prefix = m.group('p')
            if m.group('ts'):
                q = m.group('ts'); end = text.find(q, start+3)
                if end == -1:
                    self.setFormat(start, n-start, self.fmt(self.c_string))
                    self.setCurrentBlockState(self.STATE_TRIPLE_S if q=="'''" else self.STATE_TRIPLE_D); return
                self.setFormat(start, end+3-start, self.fmt(self.c_string))
                if prefix.lower()=='f': self._f_braces(text, start, end+3)
                idx = end+3; continue
            q = "'" if m.group('s') else '"'
            j = start+1+len(prefix); esc = False
            while j < n:
                ch = text[j]
                if esc: esc = False
                elif ch == '\\': esc = True
                elif ch == q: j += 1; break
                j += 1
            self.setFormat(start, j-start, self.fmt(self.c_string))
            if prefix.lower()=='f': self._f_braces(text, start, j)
            idx = j
        for m in re.finditer(r"\b(0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)\b", text):
            self.setFormat(m.start(), m.end()-m.start(), self.fmt(self.c_number))
        for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            w = m.group(0)
            if w in self.kw: self.setFormat(m.start(), m.end()-m.start(), self.fmt(self.c_kw, bold=True))
            elif w in self.builtins: self.setFormat(m.start(), m.end()-m.start(), self.fmt(self.c_type))
        for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\()", text):
            self.setFormat(m.start(), m.end()-m.start(), self.fmt(self.c_func))
        if comment_start != -1:
            self.setFormat(comment_start, n-comment_start, self.fmt(self.c_comment, italic=True))
        self.setCurrentBlockState(self.STATE_NONE)
    def _f_braces(self, text, start, end):
        seg = text[start:end]
        for i, ch in enumerate(seg):
            if ch in '{}': self.setFormat(start+i, 1, self.fmt(self.c_regex))


# ---------------- CodeEditor ----------------
class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._left_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self._left_scroll.setFixedWidth(14)
        self._left_scroll.valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().valueChanged.connect(self._left_scroll.setValue)
        self.verticalScrollBar().rangeChanged.connect(lambda a, b: self._left_scroll.setRange(a, b))

        self._zoom = 0
        self._mode = 'Plain Text'
        self._highlighter = None
        self.encoding = 'utf-8'  # Track encoding per editor
        
        self.print_line_numbers = False

        self._search_highlights = []
        self._diff_highlights = []  # Store diff highlights separately
        self._search_results = []  # List of all found positions (start, length)
        self._current_search_index = -1  # Current position in search results
        self._search_text = ""  # Current search term

        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        self.document().modificationChanged.connect(self._on_mod_changed)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def keyPressEvent(self, e):
        """Override to ensure backspace always deletes exactly 1 character and Tab inserts 4 spaces"""
        # Handle Tab key - always insert 4 spaces
        if e.key() == Qt.Key.Key_Tab and not e.modifiers():
            cursor = self.textCursor()
            cursor.insertText("    ")  # Insert 4 spaces
            return  # Don't call super() - we handled it
        
        # Force backspace to always delete exactly one character
        # regardless of tab stops or other settings
        if e.key() == Qt.Key.Key_Backspace and not e.modifiers():
            cursor = self.textCursor()
            if not cursor.hasSelection():
                # Delete exactly one character to the left
                if cursor.position() > 0:
                    cursor.deletePreviousChar()
                return  # Don't call super() - we handled it
        
        # For all other keys, use default behavior
        super().keyPressEvent(e)

    # Ensure "clicked editor" becomes the target for commands
    def focusInEvent(self, e):
        super().focusInEvent(e)
        m = self._parent_main()
        if m: 
            m._last_focused_editor = self
            m._update_encoding_status(self)

    def mousePressEvent(self, e):
        # Clicking inside the editor also sets it as target immediately
        m = self._parent_main()
        if m: m._last_focused_editor = self
        super().mousePressEvent(e)

    def _on_mod_changed(self, _changed: bool):
        main = self._parent_main()
        if not main: return
        for tabs in (main.left_tabs, main.right_tabs):
            idx = tabs.indexOf(self)
            if idx != -1:
                title = os.path.basename(getattr(self, 'path', '') or "Untitled")
                if self.document().isModified(): title = "*" + title
                tabs.setTabText(idx, title)

    def _parent_main(self):
        w = self.parent()
        while w and not isinstance(w, EditorMain):
            w = w.parent()
        return w if isinstance(w, EditorMain) else None

    def set_mode(self, mode: str, dark: bool = False):
        self._mode = mode
        self.current_mode = mode  # Store for later re-application
        if self._highlighter:
            self._highlighter.setDocument(None); self._highlighter = None
        m = mode.lower()
        if m == 'python' or 'python' in m: 
            self._highlighter = PythonHighlighter(self.document(), dark=dark)
        elif m == 'plain text':
            # Plain Text mode - no highlighter at all
            self._highlighter = None
            # CRITICAL: Clear all existing syntax highlighting formatting
            self._clear_all_formatting()
        else: 
            self._highlighter = BaseHighlighter(self.document(), dark=dark)
        
        # Clear any custom stylesheet - let the theme stylesheet control colors
        self.setStyleSheet("")
    
    def _clear_all_formatting(self):
        """Remove all character formatting from the entire document"""
        # Clear block-by-block to ensure all formatting is removed
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        
        # Iterate through all blocks (lines) and clear formatting
        block = doc.firstBlock()
        while block.isValid():
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
            # Apply default (empty) format to remove all coloring
            fmt = QTextCharFormat()
            cursor.setCharFormat(fmt)
            block = block.next()
        
        cursor.endEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

    def mode(self): return self._mode

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 4 + self.fontMetrics().horizontalAdvance('9') * digits + 12

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width() + self._left_scroll.width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        # Line number area NEVER scrolls - it's a fixed ruler!
        # Just repaint to show the correct numbers as text scrolls
        self._line_area.update()
        
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        lnw = self.line_number_area_width()
        self._left_scroll.setGeometry(QRect(cr.left(), cr.top(), self._left_scroll.width(), cr.height()))
        self._line_area.setGeometry(QRect(cr.left()+self._left_scroll.width(), cr.top(), lnw, cr.height()))

    def line_number_area_paint_event(self, e):
        """Paint line numbers as a FIXED RULER - numbers never move, text scrolls past them"""
        painter = QPainter(self._line_area)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Colors
        is_light = self.palette().window().color().lightness() > 128
        bg_color = QColor(240, 240, 240) if is_light else QColor(40, 40, 40)
        text_color = QColor(80, 80, 80) if is_light else QColor(200, 200, 200)
        
        # Fill background
        painter.fillRect(e.rect(), bg_color)
        painter.setPen(text_color)
        
        # Get line height - the fixed spacing for our ruler
        line_height = self.fontMetrics().height()
        
        # Figure out which text line is currently at the top of the viewport
        first_visible_block = self.firstVisibleBlock()
        first_line_number = first_visible_block.blockNumber()
        
        # How far has the first visible line been scrolled?
        block_top = self.blockBoundingGeometry(first_visible_block).translated(self.contentOffset()).top()
        
        # Calculate which line number should appear at the very top (Y=0) of the ruler
        # If block_top is negative, part of the first line is scrolled off
        if block_top < 0:
            # Calculate how many lines are scrolled off based on the offset
            lines_scrolled_off = int(abs(block_top) / line_height)
            top_line_number = first_line_number + lines_scrolled_off
            # Start painting at Y=0 with this line number
            start_y = int(block_top % line_height)
            if start_y < 0:
                start_y += line_height
                top_line_number += 1
        else:
            # First line is fully visible
            top_line_number = first_line_number
            start_y = int(block_top)
        
        # Now paint numbers at FIXED Y positions starting from start_y
        y_pos = start_y
        line_num = top_line_number
        
        # Paint line numbers at fixed intervals down the ruler
        while y_pos < self._line_area.height():
            # Paint this line number at its fixed position
            painter.drawText(
                0,
                y_pos,
                self._line_area.width() - 8,
                line_height,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(line_num + 1)
            )
            
            # Move to next fixed position on the ruler
            y_pos += line_height
            line_num += 1

    def highlight_current_line(self):
        if self.isReadOnly():
            self.setExtraSelections(self._search_highlights + self._diff_highlights); return
        sel = QTextEdit.ExtraSelection()
        # Improved contrast for line highlight
        is_light = self.palette().window().color().lightness() > 128
        sel.format.setBackground(QColor(255, 255, 0, 80))  # Always yellow, both modes


        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor(); sel.cursor.clearSelection()
        self.setExtraSelections([sel] + self._search_highlights + self._diff_highlights)

    def set_search_highlight(self, cursor: QTextCursor):
        s = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat(); fmt.setBackground(QColor(255, 235, 59, 220))
        s.format = fmt; s.cursor = cursor
        self._search_highlights = [s]; self.highlight_current_line()

    def clear_search_highlight(self):
        self._search_highlights = []; self.highlight_current_line()

    def paintEvent(self, event):
        super().paintEvent(event)

    def _context_menu(self, pos):
        parent = self._parent_main()
        if not parent:
            self.createStandardContextMenu().exec(self.mapToGlobal(pos)); return

        # Make THIS editor the active target for commands opened from this menu
        parent._last_focused_editor = self

        menu = self.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction(parent.zoom_in_act)
        menu.addAction(parent.zoom_out_act)
        menu.addSeparator()
        menu.addAction(parent.syntax_check_act)
        menu.addSeparator()
        menu.addAction(parent.find_act)
        menu.addAction(parent.find_next_act)
        menu.addAction(parent.find_prev_act)
        menu.addAction(parent.replace_act)
        menu.addSeparator()
        menu.addAction(parent.clear_all_highlights_act)
        menu.addSeparator()
        menu.addAction(parent.move_tab_left_act)
        menu.addAction(parent.move_tab_right_act)
        menu.addSeparator()
        menu.addAction(parent.compare_file_act)
        menu.addAction(parent.compare_with_tab_act)
        menu.addAction(parent.compare_run_act)
        menu.exec(self.mapToGlobal(pos))


# ---------------- Diff Highlighter ----------------
class DiffHighlighter:
    def __init__(self, left: QPlainTextEdit, right: QPlainTextEdit):
        self.left, self.right = left, right
    
    @staticmethod
    def clear_both(left: QPlainTextEdit, right: QPlainTextEdit):
        """Clear diff highlights from both editors"""
        for ed in (left, right):
            if not ed or not hasattr(ed, '_diff_highlights'): 
                continue
            # Clear diff highlights
            ed._diff_highlights = []
            if isinstance(ed, CodeEditor): 
                ed.highlight_current_line()

    def highlight(self) -> bool:
        """Perform diff and highlight differences - works directly with Qt blocks"""
        self.clear_both(self.left, self.right)
        
        # Bright yellow for differences
        highlight_color = QColor(255, 255, 0, 220)
        
        # Collect selections
        left_selections = []
        right_selections = []
        
        changed = False
        
        # Get block counts from documents
        left_doc = self.left.document()
        right_doc = self.right.document()
        left_block_count = left_doc.blockCount()
        right_block_count = right_doc.blockCount()
        max_blocks = max(left_block_count, right_block_count)
        
        # Compare block by block using Qt's document structure
        for block_num in range(max_blocks):
            # Get blocks directly from documents
            left_block = left_doc.findBlockByNumber(block_num)
            right_block = right_doc.findBlockByNumber(block_num)
            
            # Get text from blocks
            left_text = left_block.text() if left_block.isValid() else ""
            right_text = right_block.text() if right_block.isValid() else ""
            
            # Compare (strip trailing whitespace)
            if left_text.rstrip() != right_text.rstrip():
                changed = True
                
                # Highlight left side if not empty
                if left_text.rstrip() and left_block.isValid():
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(left_block)
                    sel.cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                    sel.format.setBackground(highlight_color)
                    left_selections.append(sel)
                
                # Highlight right side if not empty
                if right_text.rstrip() and right_block.isValid():
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(right_block)
                    sel.cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                    sel.format.setBackground(highlight_color)
                    right_selections.append(sel)
        
        # Apply highlights
        if changed:
            if hasattr(self.left, '_diff_highlights'):
                self.left._diff_highlights = left_selections
            if hasattr(self.right, '_diff_highlights'):
                self.right._diff_highlights = right_selections
            
            if isinstance(self.left, CodeEditor):
                self.left.highlight_current_line()
            if isinstance(self.right, CodeEditor):
                self.right.highlight_current_line()
        
        return changed
    
    def _add_line_selection(self, editor: QPlainTextEdit, line_num: int, 
                           color: QColor, selections: list):
        """Add a selection for an entire line"""
        block = editor.document().findBlockByLineNumber(line_num)
        if not block.isValid():
            return
        
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        selection.format.setBackground(color)
        # Removed FullWidthSelection - just highlight the line normally
        selections.append(selection)
    
    def _add_line_by_position(self, editor: QPlainTextEdit, line_num: int, 
                             total_lines: int, all_lines: list,
                             color: QColor, selections: list):
        """Highlight a line by calculating its character position in the document"""
        if line_num >= len(all_lines):
            return
        
        # Calculate the character position where this line starts
        char_pos = sum(len(all_lines[i]) + 1 for i in range(line_num))  # +1 for newline
        line_text = all_lines[line_num]
        line_length = len(line_text)
        
        if line_length == 0:
            return
        
        # Create cursor and select the entire line
        cursor = QTextCursor(editor.document())
        cursor.setPosition(char_pos)
        cursor.setPosition(char_pos + line_length, QTextCursor.MoveMode.KeepAnchor)
        
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(color)
        selections.append(selection)
    
    def _add_char_diff_selections(self, editor: QPlainTextEdit, line_num: int,
                                  this_line: str, other_line: str, 
                                  color: QColor, selections: list):
        """Add selections for specific characters that differ between two lines"""
        # Use SequenceMatcher for character-level comparison
        sm = difflib.SequenceMatcher(None, this_line, other_line, autojunk=False)
        
        block = editor.document().findBlockByLineNumber(line_num)
        if not block.isValid():
            return
        
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            
            # Create selection for the differing characters
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.cursor.setPosition(block.position() + i1)
            selection.cursor.setPosition(block.position() + i2, QTextCursor.MoveMode.KeepAnchor)
            selection.format.setBackground(color)
            selections.append(selection)
    
    def _add_full_line_content_selection(self, editor: QPlainTextEdit, line_num: int,
                                         color: QColor, selections: list):
        """Highlight the entire content of a line (for deleted/inserted lines)"""
        block = editor.document().findBlockByLineNumber(line_num)
        if not block.isValid():
            return
        
        line_text = block.text()
        if not line_text:  # Empty line
            return
        
        # Highlight from start to end of actual text content
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.cursor.setPosition(block.position())
        selection.cursor.setPosition(block.position() + len(line_text), QTextCursor.MoveMode.KeepAnchor)
        selection.format.setBackground(color)
        selections.append(selection)


# ---------------- Custom TabBar for Drag & Drop ----------------
class DraggableTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMovable(True)  # Enable built-in tab reordering
        self.drag_start_pos = None
        self.drag_tab_index = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.position().toPoint()
            self.drag_tab_index = self.tabAt(self.drag_start_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self.drag_start_pos is None or self.drag_tab_index < 0:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        # Start drag for cross-pane movement
        tab_widget = self.parent()
        if not isinstance(tab_widget, QTabWidget):
            super().mouseMoveEvent(event)
            return
            
        widget = tab_widget.widget(self.drag_tab_index)
        tab_text = tab_widget.tabText(self.drag_tab_index)
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"{id(tab_widget)}:{self.drag_tab_index}:{tab_text}")
        drag.setMimeData(mime_data)
        
        # Store widget reference in the drag object
        drag.widget = widget
        drag.tab_text = tab_text
        drag.source_tab_widget_id = id(tab_widget)
        drag.source_index = self.drag_tab_index
        
        result = drag.exec(Qt.DropAction.MoveAction)
        
        # If drag was successful and widget moved to another pane, remove from source
        if result == Qt.DropAction.MoveAction:
            # Check if widget is no longer in this tab widget
            if tab_widget.indexOf(widget) == -1:
                # Widget was moved to other pane, nothing to do
                pass

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        mime_text = event.mimeData().text()
        if not mime_text:
            event.ignore()
            return

        # Get main window
        main_win = self.window()
        if not isinstance(main_win, EditorMain):
            event.ignore()
            return

        # Parse mime data
        parts = mime_text.split(':', 2)
        if len(parts) < 3:
            event.ignore()
            return
            
        source_widget_id = int(parts[0])
        source_index = int(parts[1])
        tab_text = parts[2]

        # Find source tab widget
        if id(main_win.left_tabs) == source_widget_id:
            source_tab_widget = main_win.left_tabs
        elif id(main_win.right_tabs) == source_widget_id:
            source_tab_widget = main_win.right_tabs
        else:
            event.ignore()
            return

        target_tab_widget = self.parent()
        
        # If same tab widget, let Qt handle the reordering
        if source_tab_widget == target_tab_widget:
            event.ignore()
            return

        # Different tab widgets - move tab between panes
        widget = source_tab_widget.widget(source_index)
        if not widget:
            event.ignore()
            return

        # Remove from source
        source_tab_widget.removeTab(source_index)
        
        # Add to target at drop position
        drop_index = self.tabAt(event.position().toPoint())
        if drop_index < 0:
            drop_index = target_tab_widget.count()
        
        target_tab_widget.insertTab(drop_index, widget, tab_text)
        target_tab_widget.setCurrentIndex(drop_index)
        
        # Update focused editor
        if isinstance(widget, CodeEditor):
            main_win._last_focused_editor = widget
        
        # Enable compare mode if moved to right pane
        if target_tab_widget == main_win.right_tabs and main_win.mode != 'Compare':
            main_win.compare_toggle_act.setChecked(True)
            main_win.mode = 'Compare'
            main_win.right_tabs.show()

        event.acceptProposedAction()


# ---------------- Main Window ----------------
LANG_MODES = ["Plain Text", "Python"]

class EditorMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Editor of Death - Death's Head Software")
        self.settings = QSettings("DeathsHeadSoftware", "EditorOfDeath")
        self.word_wrap_on = False  # Always OFF by default
        self.default_encoding = self.settings.value('default_encoding', 'utf-8', type=str)
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)
        self.last_open_folder = self.settings.value("last_open_folder", "", type=str)
        self.last_save_folder = self.settings.value("last_save_folder", "", type=str)
        self.mode = 'Mono'  # or 'Compare'
        self._last_focused_editor: CodeEditor | None = None

        self._build_ui(); self.apply_theme()

        if (g := self.settings.value("geometry")): self.restoreGeometry(g)
        if (st := self.settings.value("windowState")): self.restoreState(st)
        if (sp := self.settings.value("splitter")): self.splitter.restoreState(sp)

    def _build_ui(self):
        self.resize(1400, 900)
        # Remove any size constraints to allow horizontal resizing
        self.setMinimumSize(800, 600)
        self.setMaximumSize(16777215, 16777215)  # No maximum size constraint
        
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        # Add permanent encoding label to status bar
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setStyleSheet("QLabel { padding: 2px 8px; }")
        self.status.addPermanentWidget(self.encoding_label)

        self._create_actions(); self._create_menus()

        self.splitter = QSplitter(Qt.Orientation.Horizontal); self.setCentralWidget(self.splitter)
        # Make splitter resizable
        self.splitter.setChildrenCollapsible(False)

        self.left_tabs = QTabWidget()
        self.left_tabs.setTabBar(DraggableTabBar())
        self.left_tabs.setTabsClosable(True)
        self.left_tabs.tabCloseRequested.connect(lambda i: self._close_tab_with_prompt(self.left_tabs, i))
        self.splitter.addWidget(self.left_tabs)

        self.right_tabs = QTabWidget()
        self.right_tabs.setTabBar(DraggableTabBar())
        self.right_tabs.setTabsClosable(True)
        self.right_tabs.tabCloseRequested.connect(lambda i: self._close_tab_with_prompt(self.right_tabs, i))
        self.splitter.addWidget(self.right_tabs); self.right_tabs.hide()

        # Keep target in sync when user switches tabs
        self.left_tabs.currentChanged.connect(lambda _: self._set_last_editor_from_tabs(self.left_tabs))
        self.right_tabs.currentChanged.connect(lambda _: self._set_last_editor_from_tabs(self.right_tabs))

        self._setup_tabbar_context_menus()

    def _setup_tabbar_context_menus(self):
        for tabs, side in ((self.left_tabs, 'left'), (self.right_tabs, 'right')):
            bar: QTabBar = tabs.tabBar()
            bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bar.customContextMenuRequested.connect(lambda pos, t=tabs, s=side: self._tabbar_menu(t, s, pos))

    def _tabbar_menu(self, tabs: QTabWidget, side: str, pos: QPoint):
        bar: QTabBar = tabs.tabBar()
        idx = bar.tabAt(pos)
        if idx < 0: return
        # Set target to clicked tab
        w = tabs.widget(idx)
        if isinstance(w, CodeEditor):
            self._last_focused_editor = w
        menu = QMenu(self)
        if side == 'left':
            menu.addAction("Move tab → Right Pane", lambda: self._move_tab_between(self.left_tabs, self.right_tabs, idx, auto_compare=True))
        else:
            if self.mode == 'Compare':
                menu.addAction("Move tab → Left Pane", lambda: self._move_tab_between(self.right_tabs, self.left_tabs, idx, auto_compare=False))
        menu.exec(bar.mapToGlobal(pos))

    def _set_last_editor_from_tabs(self, tabs: QTabWidget):
        w = tabs.currentWidget()
        if isinstance(w, CodeEditor):
            self._last_focused_editor = w
            self._update_encoding_status(w)
    
    def _update_encoding_status(self, ed: CodeEditor):
        """Update encoding menu checkmarks and status bar based on current editor"""
        if not isinstance(ed, CodeEditor):
            return
        encoding = getattr(ed, 'encoding', self.default_encoding)
        
        # Normalize encoding display
        display_encoding = encoding
        if encoding in ('utf-16-le', 'utf-16-be'):
            display_encoding = 'UTF-16'
        elif encoding in ('utf-32-le', 'utf-32-be'):
            display_encoding = 'UTF-32'
        elif encoding == 'utf-8-sig':
            display_encoding = 'UTF-8-BOM'
        else:
            display_encoding = encoding.upper()
        
        # Update checkmarks - find closest match
        best_match = encoding
        if encoding == 'utf-8-sig':
            best_match = 'utf-8'
        elif encoding in ('utf-16-le', 'utf-16-be'):
            best_match = 'utf-16' if 'utf-16' in self.encoding_actions else encoding
        
        for enc, act in self.encoding_actions.items():
            act.setChecked(enc == best_match)
        
        # Update status bar label
        self.encoding_label.setText(display_encoding)

    # ---------- Tab Movement ----------
    def _move_tab_between(self, src: QTabWidget, dst: QTabWidget, idx: int, auto_compare: bool = False):
        if idx < 0 or idx >= src.count(): return
        if dst is self.right_tabs and self.mode != 'Compare':
            self.compare_toggle_act.setChecked(True)
            self.mode = 'Compare'
            self.right_tabs.show()

        w = src.widget(idx); title = src.tabText(idx)
        src.removeTab(idx)
        new_idx = dst.addTab(w, title)
        dst.setCurrentIndex(new_idx)
        w.setFocus(Qt.FocusReason.OtherFocusReason)
        # Update target to moved tab
        if isinstance(w, CodeEditor):
            self._last_focused_editor = w
        if auto_compare and self.mode == 'Compare':
            self.run_compare()

    def move_tab_left(self):
        ed = self._current()
        if not isinstance(ed, CodeEditor): return
        # Where is it?
        if self.left_tabs.indexOf(ed) != -1:
            tabs = self.left_tabs
        elif self.right_tabs.indexOf(ed) != -1:
            tabs = self.right_tabs
        else:
            return
        idx = tabs.indexOf(ed)
        if tabs is self.right_tabs:
            # To other pane
            self._move_tab_between(self.right_tabs, self.left_tabs, idx, auto_compare=False)
        else:
            if idx > 0:
                t = tabs.tabText(idx)
                tabs.removeTab(idx); tabs.insertTab(idx-1, ed, t); tabs.setCurrentIndex(idx-1)

    def move_tab_right(self):
        ed = self._current()
        if not isinstance(ed, CodeEditor): return
        if self.left_tabs.indexOf(ed) != -1:
            # Move to right pane and auto compare if in compare mode
            self._move_tab_between(self.left_tabs, self.right_tabs, self.left_tabs.indexOf(ed), auto_compare=True)
        elif self.right_tabs.indexOf(ed) != -1:
            tabs = self.right_tabs
            idx = tabs.indexOf(ed)
            if idx < tabs.count()-1:
                t = tabs.tabText(idx)
                tabs.removeTab(idx); tabs.insertTab(idx+1, ed, t); tabs.setCurrentIndex(idx+1)

    # ---------- Open/Save ----------
    def _normalize_line_endings(self, text: str) -> str:
        """Normalize line endings and remove common artifacts"""
        import re
        
        # Replace CRLF with LF
        text = text.replace('\r\n', '\n')
        # Remove any remaining CR
        text = text.replace('\r', '\n')
        
        # Remove zero-width spaces and other invisible Unicode characters
        text = text.replace('\u200b', '')  # Zero-width space
        text = text.replace('\ufeff', '')  # Zero-width no-break space (BOM)
        text = text.replace('\u200c', '')  # Zero-width non-joiner
        text = text.replace('\u200d', '')  # Zero-width joiner
        text = text.replace('\u00a0', ' ')  # Non-breaking space -> regular space
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # Remove other common problematic control characters (but keep tabs and newlines)
        # Keep: \n (newline), \t (tab)
        # Remove: other control characters (0x00-0x1F except \n and \t, and 0x7F-0x9F)
        text = re.sub(r'[\x01-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        return text
    
    def _clean_text_aggressive(self, text: str) -> str:
        """Aggressively clean text - remove ALL control characters except newlines and tabs"""
        import re
        cleaned = []
        for char in text:
            code = ord(char)
            # Keep: regular printable characters, newline, tab, and common Unicode
            if (char == '\n' or char == '\t' or 
                (32 <= code <= 126) or  # ASCII printable
                (code >= 128)):  # Keep Unicode characters
                cleaned.append(char)
        result = ''.join(cleaned)
        # Normalize line endings after
        result = result.replace('\r\n', '\n').replace('\r', '\n')
        return result
    
    def _detect_encoding(self, path: str):
        """Detect file encoding by checking BOM and trying different encodings"""
        try:
            # Read first few bytes to check for BOM
            with open(path, 'rb') as f:
                raw = f.read(4)
            
            # Check for BOM (Byte Order Mark)
            if raw.startswith(b'\xff\xfe\x00\x00'):
                return 'utf-32-le'
            elif raw.startswith(b'\x00\x00\xfe\xff'):
                return 'utf-32-be'
            elif raw.startswith(b'\xff\xfe'):
                return 'utf-16-le'
            elif raw.startswith(b'\xfe\xff'):
                return 'utf-16-be'
            elif raw.startswith(b'\xef\xbb\xbf'):
                return 'utf-8-sig'
            
            # No BOM found, try to decode with different encodings
            encodings_to_try = ['utf-8', 'utf-16', 'latin-1', 'cp1252', 'iso-8859-1']
            
            for enc in encodings_to_try:
                try:
                    with open(path, 'r', encoding=enc, errors='strict') as f:
                        f.read()
                    return enc
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            # Default fallback
            return self.default_encoding
        except Exception:
            return self.default_encoding
    
    def _open_in_tabs(self, tabs: QTabWidget, path: str):
        # Detect encoding
        detected_encoding = self._detect_encoding(path)
        
        try:
            text = Path(path).read_text(encoding=detected_encoding, errors='replace')
            # Normalize line endings
            text = self._normalize_line_endings(text)
        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e))
            return None
        
        ed = self._new_tab(tabs, text)
        ed.path = path
        ed.encoding = detected_encoding
        ed.document().setModified(False)
        
        # Auto-detect and set mode based on file extension
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.py', '.pyw'):
            ed.set_mode('python', dark=self.dark_mode)
        else:
            ed.set_mode('plain text', dark=self.dark_mode)
        
        self._retitle(ed)
        self._last_focused_editor = ed
        self._update_encoding_status(ed)
        
        if detected_encoding not in ('utf-8', self.default_encoding):
            self.status.showMessage(f"Opened with {detected_encoding.upper()} encoding", 4000)
        
        return ed

    def _current(self) -> QPlainTextEdit:
        # Always prefer the last clicked editor, if it still exists
        if isinstance(self._last_focused_editor, QPlainTextEdit):
            # Make sure it's still in one of the tab widgets and hasn't been deleted
            try:
                if self.left_tabs.indexOf(self._last_focused_editor) != -1 or self.right_tabs.indexOf(self._last_focused_editor) != -1:
                    return self._last_focused_editor
            except RuntimeError:
                # Object has been deleted, clear the reference
                self._last_focused_editor = None
        # Fallbacks (rare)
        fw = QApplication.focusWidget()
        if fw and self.left_tabs.isAncestorOf(fw): return self.left_tabs.currentWidget()
        if fw and self.right_tabs.isAncestorOf(fw): return self.right_tabs.currentWidget()
        left = self.left_tabs.currentWidget(); right = self.right_tabs.currentWidget()
        return left if isinstance(left, QPlainTextEdit) else right

    def _new_tab(self, tabs: QTabWidget, text: str = ""):
        ed = CodeEditor(); ed.setPlainText(text); ed.set_mode('Plain Text', dark=self.dark_mode)
        ed.encoding = self.default_encoding  # Set default encoding for new files
        ed.setWordWrapMode(QTextOption.WrapMode.WordWrap if self.word_wrap_on else QTextOption.WrapMode.NoWrap)
        ed.document().setModified(bool(text))
        idx = tabs.addTab(ed, ("*Untitled" if ed.document().isModified() else "Untitled"))
        tabs.setCurrentIndex(idx); ed.setFocus()
        # new tab becomes target
        self._last_focused_editor = ed
        self._update_encoding_status(ed)
        return ed

    def _retitle(self, ed: QPlainTextEdit):
        title = os.path.basename(getattr(ed, 'path', '') or "Untitled")
        if ed.document().isModified(): title = "*" + title
        tabs = self.left_tabs if self.left_tabs.indexOf(ed) != -1 else self.right_tabs
        i = tabs.indexOf(ed)
        if i >= 0: tabs.setTabText(i, title)

    def _maybe_save_editor(self, ed: QPlainTextEdit) -> bool:
        if not isinstance(ed, QPlainTextEdit) or not ed.document().isModified():
            return True
        title = os.path.basename(getattr(ed, 'path', '') or "Untitled")
        btn = QMessageBox.question(
            self, "Save Changes?",
            f'"{title}" has unsaved changes.\n\nSave before closing?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )
        if btn == QMessageBox.StandardButton.Save:
            return self._save_widget(ed)
        elif btn == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def _close_tab_with_prompt(self, tabs: QTabWidget, index: int):
        w = tabs.widget(index)
        # set target to the tab being closed
        if isinstance(w, CodeEditor):
            self._last_focused_editor = w
        if not self._maybe_save_editor(w): return
        tabs.removeTab(index); w.deleteLater()

    def closeEvent(self, e):
        for tabs in (self.left_tabs, self.right_tabs):
            for i in range(tabs.count()):
                if not self._maybe_save_editor(tabs.widget(i)):
                    e.ignore(); return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.setValue('word_wrap_on', self.word_wrap_on)
        self.settings.setValue('default_encoding', self.default_encoding)
        self.settings.setValue('dark_mode', self.dark_mode)
        self.settings.setValue('last_open_folder', self.last_open_folder)
        self.settings.setValue('last_save_folder', self.last_save_folder)
        super().closeEvent(e)

    # File API (always operate on clicked/target tab)
    def file_new(self):
        ed = self._current()
        # open next to the clicked tab's pane
        if self.left_tabs.indexOf(ed) != -1:
            self._new_tab(self.left_tabs)
        elif self.right_tabs.indexOf(ed) != -1:
            self._new_tab(self.right_tabs)
        else:
            self._new_tab(self.left_tabs)
    def file_open(self):
        # Use last open folder if available, otherwise empty string
        start_dir = self.last_open_folder if self.last_open_folder and os.path.isdir(self.last_open_folder) else ""
        paths, _ = QFileDialog.getOpenFileNames(self, "Open", start_dir, "All Files (*.*)")
        if not paths: return
        
        # Save the folder from the first file opened
        if paths:
            self.last_open_folder = os.path.dirname(paths[0])
            self.settings.setValue('last_open_folder', self.last_open_folder)
        
        ed = self._current()
        if self.right_tabs.indexOf(ed) != -1:
            target_tabs = self.right_tabs
        else:
            target_tabs = self.left_tabs
        
        # Open all selected files
        for path in paths:
            self._open_in_tabs(target_tabs, path)
    def _save_widget(self, ed: QPlainTextEdit) -> bool:
        if not getattr(ed, 'path', None): return self._save_as_widget(ed)
        try:
            encoding = getattr(ed, 'encoding', self.default_encoding)
            text = ed.toPlainText()
            
            # Normalize line endings before saving (ensure Unix LF)
            text = self._normalize_line_endings(text)
            
            # Write file with proper encoding and line ending control
            with open(ed.path, 'w', encoding=encoding, errors='replace', newline='\n') as f:
                f.write(text)
            
            ed.document().setModified(False)
            self._retitle(ed)
            
            # Show detailed save message
            file_size = Path(ed.path).stat().st_size
            self.status.showMessage(f"✓ Saved: {os.path.basename(ed.path)} ({encoding.upper()}, {file_size} bytes)", 4000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")
            return False
    def _save_as_widget(self, ed: QPlainTextEdit) -> bool:
        # Determine starting directory
        # Priority: 1. Current file's directory, 2. Last save folder, 3. Last open folder, 4. Empty
        current_path = getattr(ed, 'path', None)
        if current_path and os.path.isfile(current_path):
            start_path = current_path
        elif self.last_save_folder and os.path.isdir(self.last_save_folder):
            start_path = os.path.join(self.last_save_folder, "Untitled.txt")
        elif self.last_open_folder and os.path.isdir(self.last_open_folder):
            start_path = os.path.join(self.last_open_folder, "Untitled.txt")
        else:
            start_path = "Untitled.txt"
        
        path, _ = QFileDialog.getSaveFileName(self, "Save As", start_path, "All Files (*.*)")
        if not path: return False
        
        # Save the folder for future saves
        self.last_save_folder = os.path.dirname(path)
        self.settings.setValue('last_save_folder', self.last_save_folder)
        
        ed.path = path
        # Preserve the current encoding when saving with new name
        if not hasattr(ed, 'encoding'):
            ed.encoding = self.default_encoding
        self._retitle(ed)
        return self._save_widget(ed)
    def file_save(self):
        ed = self._current()
        if ed: 
            self._save_widget(ed)
            if isinstance(ed, CodeEditor):
                self._update_encoding_status(ed)
    def file_save_as(self):
        ed = self._current()
        if ed:
            self._save_as_widget(ed)
            if isinstance(ed, CodeEditor):
                self._update_encoding_status(ed)
    def file_close_tab(self):
        ed = self._current()
        if self.left_tabs.indexOf(ed) != -1:
            self._close_tab_with_prompt(self.left_tabs, self.left_tabs.indexOf(ed))
        elif self.right_tabs.indexOf(ed) != -1:
            self._close_tab_with_prompt(self.right_tabs, self.right_tabs.indexOf(ed))

    def file_print(self):
        ed = self._current()
        if not ed: return
        
        # Ask about line numbers
        reply = QMessageBox.question(
            self, 
            "Print Options",
            "Include line numbers?\n\nYes = code with line numbers\nNo = document without line numbers",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Cancel:
            return
        
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec():
            if reply == QMessageBox.StandardButton.Yes:
                self._print_with_line_numbers(ed, printer)
            else:
                ed.document().print(printer)
    
    def _print_with_line_numbers(self, editor, printer):
        """Print with line numbers"""
        from PyQt6.QtGui import QTextDocument, QTextCursor
        
        doc = QTextDocument()
        cursor = QTextCursor(doc)
        
        text = editor.toPlainText()
        lines = text.split('\n')
        
        width = len(str(len(lines)))
        
        for i, line in enumerate(lines, 1):
            cursor.insertText(f"{str(i).rjust(width)} | {line}\n")
        
        doc.print(printer)

    def file_save_as_pdf(self):
        """Save current document as PDF"""
        ed = self._current()
        if not ed:
            QMessageBox.information(self, "Save as PDF", "No document open.")
            return
        
        # Ask about line numbers
        reply = QMessageBox.question(
            self, 
            "PDF Options",
            "Include line numbers?\n\nYes = code with line numbers\nNo = document without line numbers",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Cancel:
            return
        
        # Get save path
        default_name = os.path.basename(getattr(ed, 'path', '') or "Untitled")
        default_name = os.path.splitext(default_name)[0] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save as PDF", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        
        # Create printer and print to PDF
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        
        # Print the document
        if reply == QMessageBox.StandardButton.Yes:
            self._print_with_line_numbers(ed, printer)
        else:
            ed.document().print(printer)
        
        self.status.showMessage(f"Saved as PDF: {path}", 3000)
        QMessageBox.information(self, "Save as PDF", f"Document saved to:\n{path}")

    # ---------- Edit / Find / Highlights (targeted via _current) ----------
    def edit_delete(self):
        ed = self._current()
        if not ed: return
        c = ed.textCursor()
        if c.hasSelection(): c.removeSelectedText()
        else: c.deleteChar()
    def edit_find(self):
        ed = self._current()
        if not ed: return
        text, ok = QInputDialog.getText(self, "Find", "Find:")
        if ok and text:
            self._find_all(text)
    def edit_replace(self):
        '''Replace all occurrences and highlight them for navigation'''
        ed = self._current()
        if not ed:
            return
        
        find, ok = QInputDialog.getText(self, "Replace", "Find:")
        if not ok or not find:
            return
        
        repl, ok2 = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok2:
            return
        
        # Ask if whole word only
        msg = QMessageBox()
        msg.setWindowTitle("Replace Options")
        msg.setText("Match whole words only?")
        msg.setInformativeText("If Yes, 'def' will only match 'def' as a complete word, not 'define' or 'ifdef'")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        result = msg.exec()
        
        if result == QMessageBox.StandardButton.Cancel:
            return
        
        whole_word = (result == QMessageBox.StandardButton.Yes)
        
        # Find all occurrences before replacing
        doc_text = ed.toPlainText()
        find_len = len(find)
        repl_len = len(repl)
        positions = []
        pos = 0
        
        if whole_word:
            # Use regex to find whole words only
            import re
            pattern = r'\b' + re.escape(find) + r'\b'
            for match in re.finditer(pattern, doc_text):
                positions.append(match.start())
        else:
            # Find all substrings
            while True:
                pos = doc_text.find(find, pos)
                if pos == -1:
                    break
                positions.append(pos)
                pos += 1
        
        if not positions:
            QMessageBox.information(self, "Replace", "No occurrences found.")
            return
        
        count = len(positions)
        
        # Show preview of what will be replaced
        preview_lines = []
        for pos in positions[:10]:  # Show first 10
            # Find the line containing this position
            line_start = doc_text.rfind('\n', 0, pos) + 1
            line_end = doc_text.find('\n', pos)
            if line_end == -1:
                line_end = len(doc_text)
            line = doc_text[line_start:line_end]
            line_num = doc_text[:pos].count('\n') + 1
            preview_lines.append(f"Line {line_num}: {line[:80]}")
        
        preview = "\n".join(preview_lines)
        if count > 10:
            preview += f"\n... and {count - 10} more"
        
        confirm = QMessageBox.question(
            self,
            "Replace Confirmation",
            f"Found {count} occurrence(s).\n\nPreview:\n{preview}\n\nReplace all?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        # Replace all (undo/redo-safe)
        cursor = ed.textCursor()
        cursor.beginEditBlock()
        
        # Replace from end to beginning to maintain position validity
        for pos in reversed(positions):
            cursor.setPosition(pos)
            cursor.setPosition(pos + find_len, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(repl)
        
        cursor.endEditBlock()
        ed.document().setModified(True)
        self._retitle(ed)
        
        # Calculate new positions after replacement (position shift)
        shift = repl_len - find_len
        new_positions = []
        for i, pos in enumerate(positions):
            # Each replacement shifts all subsequent positions
            adjusted_pos = pos + (shift * i)
            new_positions.append((adjusted_pos, repl_len))
        
        # Store as search results for navigation
        ed._search_results = new_positions
        ed._search_text = repl
        ed._current_search_index = 0
        
        # Highlight all replaced items
        highlights = []
        for start_pos, length in new_positions:
            cursor = QTextCursor(ed.document())
            cursor.setPosition(start_pos)
            cursor.setPosition(start_pos + length, QTextCursor.MoveMode.KeepAnchor)
            
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 200, 0, 180))  # Orange-yellow for replaced items
            sel.format = fmt
            sel.cursor = cursor
            highlights.append(sel)
        
        ed._search_highlights = highlights
        ed.highlight_current_line()
        
        # Jump to first replaced item
        first_pos, first_len = new_positions[0]
        cursor = ed.textCursor()
        cursor.setPosition(first_pos)
        cursor.setPosition(first_pos + first_len, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cursor)
        ed.centerCursor()
        
        QMessageBox.information(
            self, 
            "Replace", 
            f"Replaced {count} occurrence(s).\n\nUse Find Next/Previous to navigate through replaced items."
        )
    def _find_all(self, text: str):
        '''Find all occurrences, highlight them, and jump to first'''
        ed = self._current()
        if not ed or not text:
            return
        
        # Clear previous search
        ed._search_results = []
        ed._search_text = text
        ed._current_search_index = -1
        
        # Find all occurrences
        doc_text = ed.toPlainText()
        search_len = len(text)
        pos = 0
        
        while True:
            pos = doc_text.find(text, pos)
            if pos == -1:
                break
            ed._search_results.append((pos, search_len))
            pos += 1  # Move by 1 to find overlapping matches
        
        if not ed._search_results:
            QMessageBox.information(self, "Find", "No occurrences found.")
            ed._search_highlights = []
            ed.highlight_current_line()
            return
        
        # Highlight all occurrences
        highlights = []
        for start_pos, length in ed._search_results:
            cursor = QTextCursor(ed.document())
            cursor.setPosition(start_pos)
            cursor.setPosition(start_pos + length, QTextCursor.MoveMode.KeepAnchor)
            
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 255, 0, 180))  # Yellow highlight
            sel.format = fmt
            sel.cursor = cursor
            highlights.append(sel)
        
        ed._search_highlights = highlights
        ed.highlight_current_line()
        
        # Jump to first occurrence
        ed._current_search_index = 0
        first_pos, first_len = ed._search_results[0]
        cursor = ed.textCursor()
        cursor.setPosition(first_pos)
        cursor.setPosition(first_pos + first_len, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cursor)
        ed.centerCursor()
        
        self.status.showMessage(f"Found {len(ed._search_results)} occurrence(s). Use Find Next/Previous to navigate.", 3000)
    
    def _find(self, text: str, forward=True, case=False):
        '''Legacy find method - redirects to _find_all'''
        self._find_all(text)
    def _find_again(self, forward=True):
        '''Navigate to next or previous search result'''
        ed = self._current()
        if not ed:
            return
        
        # If no search results, try to search for selected text
        if not ed._search_results:
            text = ed.textCursor().selectedText()
            if text:
                self._find_all(text)
            return
        
        # Navigate through search results
        if forward:
            ed._current_search_index = (ed._current_search_index + 1) % len(ed._search_results)
        else:
            ed._current_search_index = (ed._current_search_index - 1) % len(ed._search_results)
        
        # Jump to current result
        pos, length = ed._search_results[ed._current_search_index]
        cursor = ed.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cursor)
        ed.centerCursor()
        
        self.status.showMessage(
            f"Result {ed._current_search_index + 1} of {len(ed._search_results)}", 
            2000
        )
    def clear_search_highlight(self):
        ed = self._current()
        if isinstance(ed, CodeEditor):
            ed.clear_search_highlight()
            self.status.showMessage("Search highlight cleared.", 2000)
    def clear_all_highlights(self):
        left = self.left_tabs.currentWidget(); right = self.right_tabs.currentWidget()
        if isinstance(left, CodeEditor):  left.clear_search_highlight()
        if isinstance(right, CodeEditor): right.clear_search_highlight()
        DiffHighlighter.clear_both(left, right)
        self.status.showMessage("All highlights cleared (search & compare).", 2500)

    # ---------- View / Theme ----------
    def apply_theme(self):
        if self.dark_mode:
            # Dark mode with white text
            self.setStyleSheet("""
                QMainWindow, QWidget { background-color: #1e1e1e; color: #ffffff; }
                QMenuBar { background-color: #2d2d30; color: #ffffff; }
                QMenuBar::item:selected { background-color: #3e3e42; }
                QMenu { background-color: #2d2d30; color: #ffffff; }
                QMenu::item:selected { background-color: #3e3e42; }
                QPlainTextEdit { background-color: #1e1e1e; color: #ffffff; selection-background-color: #ffff00; selection-color: #000000; }
                QTabBar::tab { background:#2d2d30; color:#ffffff; padding:6px 12px; }
                QTabBar::tab:selected { background:#1e1e1e; border-bottom:2px solid #0e639c; }
                QStatusBar { background-color: #000000; color: #ffffff; }
                QLabel { color: #ffffff; }
            """)
        else:
            # Light mode (original)
            self.setStyleSheet("""
                QMainWindow, QWidget { background-color: #f5f5f5; color: #000; }
                QMenuBar { background-color: #ffffff; color: #000; }
                QMenu { background-color: #ffffff; color: #000; }
                QPlainTextEdit { background-color: #ffffff; color: #000; selection-background-color: #ffd966; selection-color: #000; }
                QTabBar::tab { background:#e0e0e0; color:#000; padding:6px 12px; }
                QTabBar::tab:selected { background:#ffffff; border-bottom:2px solid #0078d4; }
            """)
        
        # Update syntax highlighting for all open editors
        for tabs in [self.left_tabs, self.right_tabs]:
            for i in range(tabs.count()):
                ed = tabs.widget(i)
                if isinstance(ed, CodeEditor):
                    # Re-apply the current mode to update the highlighter
                    current_mode = getattr(ed, 'current_mode', 'plain text')
                    ed.set_mode(current_mode, dark=self.dark_mode)
    
    def toggle_dark_mode(self):
        """Toggle between dark mode and light mode"""
        self.dark_mode = self.dark_mode_act.isChecked()
        self.settings.setValue('dark_mode', self.dark_mode)
        self.apply_theme()
        mode_text = "Dark Mode" if self.dark_mode else "Light Mode"
        self.status.showMessage(f"Switched to {mode_text}", 2000)
    def format_toggle_wrap(self):
        self.word_wrap_on = self.word_wrap_act.isChecked()
        self.settings.setValue('word_wrap_on', self.word_wrap_on)
        for tabs in [self.left_tabs, self.right_tabs]:
            for i in range(tabs.count()):
                ed = tabs.widget(i)
                if isinstance(ed, QPlainTextEdit):
                    ed.setWordWrapMode(QTextOption.WrapMode.WordWrap if self.word_wrap_on else QTextOption.WrapMode.NoWrap)
    def format_font(self):
        ed = self._current()
        if not ed: return
        font, ok = QFontDialog.getFont(ed.font(), self, "Choose Font")
        if ok:
            for tabs in [self.left_tabs, self.right_tabs]:
                for i in range(tabs.count()):
                    w = tabs.widget(i)
                    if isinstance(w, QPlainTextEdit):
                        w.setFont(font)
    
    def zoom_in(self):
        """Increase font size"""
        ed = self._current()
        if not ed: return
        current_font = ed.font()
        new_size = current_font.pointSize() + 1
        current_font.setPointSize(new_size)
        for tabs in [self.left_tabs, self.right_tabs]:
            for i in range(tabs.count()):
                w = tabs.widget(i)
                if isinstance(w, QPlainTextEdit):
                    font = w.font()
                    font.setPointSize(new_size)
                    w.setFont(font)
        self.status.showMessage(f"Font size: {new_size}", 2000)
    
    def zoom_out(self):
        """Decrease font size"""
        ed = self._current()
        if not ed: return
        current_font = ed.font()
        new_size = max(6, current_font.pointSize() - 1)  # Minimum size of 6
        current_font.setPointSize(new_size)
        for tabs in [self.left_tabs, self.right_tabs]:
            for i in range(tabs.count()):
                w = tabs.widget(i)
                if isinstance(w, QPlainTextEdit):
                    font = w.font()
                    font.setPointSize(new_size)
                    w.setFont(font)
        self.status.showMessage(f"Font size: {new_size}", 2000)
    
    def set_encoding(self, encoding: str):
        ed = self._current()
        if ed and isinstance(ed, CodeEditor):
            old_encoding = getattr(ed, 'encoding', 'utf-8')
            # Change encoding for current file
            ed.encoding = encoding
            if old_encoding != encoding:
                ed.document().setModified(True)  # Mark as modified since encoding changed
                self._retitle(ed)
                msg = f"Encoding changed: {old_encoding.upper()} → {encoding.upper()}. SAVE to convert the file."
                self.status.showMessage(msg, 6000)
                QMessageBox.information(self, "Encoding Changed", 
                    f"File encoding changed from {old_encoding.upper()} to {encoding.upper()}.\n\n"
                    f"The file will be CONVERTED and saved with {encoding.upper()} encoding when you save.\n\n"
                    f"Current encoding: {old_encoding.upper()}\n"
                    f"New encoding (on save): {encoding.upper()}")
            self._update_encoding_status(ed)
        else:
            # No file open, just set default
            self.default_encoding = encoding
            self.settings.setValue('default_encoding', encoding)
            self.status.showMessage(f"Default encoding for new files set to {encoding.upper()}", 3000)
        
        # Update checkmarks
        for enc, act in self.encoding_actions.items():
            act.setChecked(enc == encoding)
    
    def fix_garbled_text(self):
        """Help user fix garbled text by trying different encodings"""
        ed = self._current()
        if not isinstance(ed, CodeEditor):
            QMessageBox.information(self, "Fix Garbled Text", "No file open.")
            return
        
        path = getattr(ed, 'path', None)
        if not path:
            QMessageBox.information(self, "Fix Garbled Text", "File has not been saved yet.\n\nSave the file first, then use this feature.")
            return
        
        # Check if modified
        if ed.document().isModified():
            btn = QMessageBox.question(
                self, "Unsaved Changes",
                "File has unsaved changes. These changes will be lost.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if btn != QMessageBox.StandardButton.Yes:
                return
        
        # Create preview dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Fix Garbled Text - Preview Encodings")
        dlg.resize(800, 600)
        
        layout = QVBoxLayout(dlg)
        
        # Instructions
        instructions = QLabel(
            "Select the encoding that displays the text correctly.\n"
            "Current encoding: " + getattr(ed, 'encoding', 'utf-8').upper()
        )
        layout.addWidget(instructions)
        
        # Split view
        h_layout = QHBoxLayout()
        
        # Left: encoding list
        enc_list = QListWidget()
        enc_list.setMaximumWidth(200)
        h_layout.addWidget(enc_list)
        
        # Right: preview
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        h_layout.addWidget(preview)
        
        layout.addLayout(h_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        clean_btn = QPushButton("Clean Artifacts")
        clean_btn.setToolTip("Remove control characters and artifacts from current preview")
        use_btn = QPushButton("Use This Encoding")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(clean_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(use_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        # Try different encodings
        encodings = [
            ('UTF-8', 'utf-8'),
            ('UTF-8 with BOM', 'utf-8-sig'),
            ('UTF-16', 'utf-16'),
            ('UTF-16 LE', 'utf-16-le'),
            ('UTF-16 BE', 'utf-16-be'),
            ('UTF-32', 'utf-32'),
            ('UTF-32 LE', 'utf-32-le'),
            ('UTF-32 BE', 'utf-32-be'),
            ('Windows-1252 (CP1252)', 'cp1252'),
            ('Latin-1 (ISO-8859-1)', 'latin-1'),
            ('ASCII', 'ascii'),
        ]
        
        previews = {}
        for display_name, enc_name in encodings:
            try:
                text = Path(path).read_text(encoding=enc_name, errors='replace')
                # Normalize line endings to remove artifacts
                text = self._normalize_line_endings(text)
                previews[display_name] = (enc_name, text)
                enc_list.addItem(display_name)
            except Exception:
                pass
        
        selected_encoding = [None]
        is_cleaned = [False]  # Track if aggressive cleaning was applied
        
        def on_selection_changed():
            current = enc_list.currentItem()
            if current and current.text() in previews:
                enc_name, text = previews[current.text()]
                # Show first 2000 characters
                preview.setPlainText(text[:2000] + ("..." if len(text) > 2000 else ""))
                selected_encoding[0] = enc_name
                is_cleaned[0] = False  # Reset cleaned flag when changing encoding
        
        def on_clean_artifacts():
            """Apply aggressive cleaning to remove control characters"""
            current = enc_list.currentItem()
            if current and current.text() in previews:
                enc_name, text = previews[current.text()]
                # Apply aggressive cleaning
                cleaned_text = self._clean_text_aggressive(text)
                # Update preview
                preview.setPlainText(cleaned_text[:2000] + ("..." if len(cleaned_text) > 2000 else ""))
                # Store cleaned version
                previews[current.text()] = (enc_name, cleaned_text)
                is_cleaned[0] = True
                self.status.showMessage("Artifacts removed from preview", 2000)
        
        def on_use():
            if selected_encoding[0]:
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "No Selection", "Please select an encoding first.")
        
        enc_list.currentItemChanged.connect(lambda: on_selection_changed())
        clean_btn.clicked.connect(on_clean_artifacts)
        use_btn.clicked.connect(on_use)
        cancel_btn.clicked.connect(dlg.reject)
        
        # Select current encoding if available
        current_enc = getattr(ed, 'encoding', 'utf-8')
        for i in range(enc_list.count()):
            item = enc_list.item(i)
            if item.text() in previews and previews[item.text()][0] == current_enc:
                enc_list.setCurrentItem(item)
                break
        
        if enc_list.count() > 0 and enc_list.currentItem() is None:
            enc_list.setCurrentRow(0)
        
        on_selection_changed()
        
        if dlg.exec() and selected_encoding[0]:
            # Apply selected encoding
            try:
                # Get the text from previews (which may have been cleaned)
                current = enc_list.currentItem()
                if current and current.text() in previews:
                    enc_name, text = previews[current.text()]
                else:
                    # Fallback: read from file
                    text = Path(path).read_text(encoding=selected_encoding[0], errors='replace')
                    text = self._normalize_line_endings(text)
                
                ed.setPlainText(text)
                ed.encoding = selected_encoding[0]
                ed.document().setModified(True if is_cleaned[0] else False)  # Mark modified if cleaned
                self._retitle(ed)
                self._update_encoding_status(ed)
                
                display_enc = selected_encoding[0].upper()
                if selected_encoding[0] in ('utf-16-le', 'utf-16-be'):
                    display_enc = 'UTF-16'
                
                msg = f"✓ Fixed! Now using {display_enc} encoding"
                if is_cleaned[0]:
                    msg += " (artifacts removed)"
                self.status.showMessage(msg, 4000)
                
                info_msg = f"Text should now display correctly.\n\nEncoding: {display_enc}"
                if is_cleaned[0]:
                    info_msg += "\n\nNote: Artifacts were removed. Save the file to keep these changes."
                else:
                    info_msg += "\n\nIf you still see artifacts (squares), reopen this dialog and click 'Clean Artifacts'."
                info_msg += "\n\nTo convert to UTF-8:\n1. Encoding menu → UTF-8\n2. Save the file"
                
                QMessageBox.information(self, "Success", info_msg)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply encoding:\n{e}")
    
    def remove_artifacts(self):
        """Remove control characters and artifacts from current document"""
        ed = self._current()
        if not isinstance(ed, CodeEditor):
            QMessageBox.information(self, "Remove Artifacts", "No file open.")
            return
        
        text = ed.toPlainText()
        if not text:
            QMessageBox.information(self, "Remove Artifacts", "Document is empty.")
            return
        
        # Show preview of what will be removed
        btn = QMessageBox.question(
            self, "Remove Artifacts",
            "This will remove all control characters and invisible characters from the document.\n\n"
            "Examples of what will be removed:\n"
            "• Null bytes\n"
            "• Carriage returns (keeping newlines)\n"
            "• Control characters that display as squares\n"
            "• Zero-width spaces\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if btn != QMessageBox.StandardButton.Yes:
            return
        
        # Apply aggressive cleaning
        cleaned_text = self._clean_text_aggressive(text)
        
        # Check if anything changed
        if cleaned_text == text:
            QMessageBox.information(self, "Remove Artifacts", "No artifacts found. Document is already clean.")
            return
        
        # Apply changes
        ed.setPlainText(cleaned_text)
        ed.document().setModified(True)
        self._retitle(ed)
        
        # Calculate stats
        removed_count = len(text) - len(cleaned_text)
        self.status.showMessage(f"✓ Removed {removed_count} artifact character(s)", 4000)
        QMessageBox.information(self, "Success", 
            f"Artifacts removed!\n\n"
            f"Removed {removed_count} character(s)\n\n"
            f"Save the file to keep these changes.")
    
    # ---------- Tools: hashing ----------
    def compute_hash(self, algo: str, from_file: bool):
        try:
            h = getattr(hashlib, algo)()
        except AttributeError:
            QMessageBox.critical(self, "Error", f"Unsupported algorithm: {algo}")
            return
        if from_file:
            path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*.*)")
            if not path: return
            try:
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b''):
                        h.update(chunk)
            except Exception as e:
                QMessageBox.critical(self, "Hash Error", str(e)); return
            digest = h.hexdigest()
            QApplication.clipboard().setText(digest)
            QMessageBox.information(self, algo.upper(), f"{algo.upper()}({os.path.basename(path)}) =\n{digest}\n\n✅ Copied to clipboard.")
            self.status.showMessage(f"{algo.upper()} copied to clipboard", 3000)
        else:
            ed = self._current()
            if not ed: return
            data = ed.toPlainText().encode('utf-8', errors='replace')
            h.update(data)
            digest = h.hexdigest()
            QApplication.clipboard().setText(digest)
            QMessageBox.information(self, algo.upper(), f"{algo.upper()}(document) =\n{digest}\n\n✅ Copied to clipboard.")
            self.status.showMessage(f"{algo.upper()} copied to clipboard", 3000)

    # ---------- Mode ----------
    def set_code_mode(self, mode: str):
        ed = self._current()
        if not ed: return
        
        # Only Plain Text or Python
        if 'python' in mode.lower(): 
            lang = 'python'
        else: 
            lang = 'plain text'
        
        ed.set_mode(lang, dark=self.dark_mode)
        self.status.showMessage(f"Mode: {mode}", 2000)

    # ---------- Compare (clicked-tab aware) ----------
    def toggle_compare(self):
        self.mode = 'Compare' if self.compare_toggle_act.isChecked() else 'Mono'
        if self.mode == 'Compare':
            self.right_tabs.show()
            self.status.showMessage("Compare Mode enabled.", 2500)
        else:
            self.right_tabs.hide()
            DiffHighlighter.clear_both(self.left_tabs.currentWidget(), self.right_tabs.currentWidget())
            self.status.showMessage("Compare Mode disabled.", 2500)

    def compare_with_file(self):
        base_ed = self._current()
        if not isinstance(base_ed, CodeEditor):
            QMessageBox.information(self, "Compare", "Click a document first."); return
        # Determine opposite pane for the comparison partner
        base_on_left = (self.left_tabs.indexOf(base_ed) != -1)
        other_tabs = self.right_tabs if base_on_left else self.left_tabs
        if self.mode != 'Compare':
            self.compare_toggle_act.setChecked(True); self.mode = 'Compare'; self.right_tabs.show()
        
        # Use last open folder if available
        start_dir = self.last_open_folder if self.last_open_folder and os.path.isdir(self.last_open_folder) else ""
        path, _ = QFileDialog.getOpenFileName(self, "Compare with File…", start_dir, "All Files (*.*)")
        if not path: return
        
        # Save the folder
        self.last_open_folder = os.path.dirname(path)
        self.settings.setValue('last_open_folder', self.last_open_folder)
        
        try:
            other_text = Path(path).read_text(encoding=self.default_encoding, errors='replace')
        except Exception as e:
            QMessageBox.critical(self, "Compare", f"Failed to read file:\n{e}"); return
        if other_tabs.count() == 0:
            other_ed = self._new_tab(other_tabs, other_text)
        else:
            other_ed = other_tabs.currentWidget()
            if not isinstance(other_ed, CodeEditor):
                other_ed = self._new_tab(other_tabs, "")
            other_ed.setPlainText(other_text)
        other_ed.path = path; other_ed.document().setModified(False); self._retitle(other_ed)
        self.run_compare()

    def compare_with_open_tab_picker(self):
        base = self._current()
        if not isinstance(base, CodeEditor):
            QMessageBox.information(self, "Compare", "Click a document first."); return

        all_items = []
        def collect(tabs: QTabWidget, label: str):
            for i in range(tabs.count()):
                w = tabs.widget(i); title = tabs.tabText(i)
                all_items.append((label, tabs, i, title, w))
        collect(self.left_tabs, "Left"); collect(self.right_tabs, "Right")
        if len(all_items) <= 1:
            QMessageBox.information(self, "Compare", "Open another tab to compare with."); return

        dlg = QDialog(self); dlg.setWindowTitle("Compare with… (open tab)")
        dlg.resize(480, 380)
        v = QVBoxLayout(dlg)
        lst = QListWidget(dlg); v.addWidget(lst)
        for side, tabs, idx, title, w in all_items:
            if w is base: continue
            item = QListWidgetItem(f"[{side}] {title}")
            item.setData(Qt.ItemDataRole.UserRole, (side, tabs, idx, title, w))
            lst.addItem(item)
        btns = QHBoxLayout(); ok = QPushButton("Compare"); cancel = QPushButton("Cancel")
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cancel); v.addLayout(btns)
        chosen = {}
        def do_ok():
            it = lst.currentItem()
            if not it: return
            chosen["sel"] = it.data(Qt.ItemDataRole.UserRole); dlg.accept()
        ok.clicked.connect(do_ok); cancel.clicked.connect(dlg.reject)
        if not dlg.exec(): return
        side, tabs, idx, title, w = chosen["sel"]
        # Ensure compare mode and place partner on opposite side of base
        if self.mode != 'Compare':
            self.compare_toggle_act.setChecked(True); self.mode = 'Compare'; self.right_tabs.show()
        if self.left_tabs.indexOf(base) != -1:
            # base is left → ensure chosen ends up right
            if tabs is self.right_tabs:
                self.right_tabs.setCurrentIndex(idx)
            else:
                self._move_tab_between(self.left_tabs, self.right_tabs, idx, auto_compare=False)
        else:
            # base is right → ensure chosen ends up left
            if tabs is self.left_tabs:
                self.left_tabs.setCurrentIndex(idx)
            else:
                self._move_tab_between(self.right_tabs, self.left_tabs, idx, auto_compare=False)
        self.run_compare()

    def run_compare(self):
        if self.mode != 'Compare':
            QMessageBox.information(self, "Compare", "Enable Compare Mode first."); return
        left = self.left_tabs.currentWidget(); right = self.right_tabs.currentWidget()
        if not isinstance(left, CodeEditor) or not isinstance(right, CodeEditor):
            QMessageBox.warning(self, "Compare", "Open a document in each side."); return
        
        # Switch both editors to Plain Text mode to disable syntax highlighting
        # This allows diff highlights to be clearly visible
        left.set_mode('Plain Text', dark=self.dark_mode)
        right.set_mode('Plain Text', dark=self.dark_mode)
        
        highlighter = DiffHighlighter(left, right)
        changed = highlighter.highlight()
        if not changed:
            self.status.showMessage("No differences found.", 3500)
            return
        self.status.showMessage("Different lines highlighted in yellow", 4000)

    # ---------- Actions / Menus ----------
    def _create_actions(self):
        # File
        self.new_act = QAction("New", self, shortcut=QKeySequence.StandardKey.New, triggered=self.file_new)
        self.open_act = QAction("Open", self, shortcut=QKeySequence.StandardKey.Open, triggered=self.file_open)
        self.save_act = QAction("Save", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.file_save)
        self.save_as_act = QAction("Save As", self, shortcut=QKeySequence("Ctrl+Shift+S"), triggered=self.file_save_as)
        self.save_as_pdf_act = QAction("Save text as PDF", self, shortcut=QKeySequence("Ctrl+P"), triggered=self.file_save_as_pdf)
        self.print_act = QAction("Print", self, shortcut=QKeySequence.StandardKey.Print, triggered=self.file_print)
        self.close_tab_act = QAction("Close", self, shortcut=QKeySequence.StandardKey.Close, triggered=self.file_close_tab)
        self.exit_act = QAction("Exit", self, triggered=self.close)

        # Edit
        self.undo_act = QAction("Undo", self, shortcut=QKeySequence.StandardKey.Undo,
                                triggered=lambda: self._current() and self._current().undo())
        self.redo_act = QAction("Redo", self, shortcut=QKeySequence("Ctrl+Y"),
                                triggered=lambda: self._current() and self._current().redo())
        self.cut_act = QAction("Cut", self, shortcut=QKeySequence.StandardKey.Cut,
                               triggered=lambda: self._current() and self._current().cut())
        self.copy_act = QAction("Copy", self, shortcut=QKeySequence.StandardKey.Copy,
                                triggered=lambda: self._current() and self._current().copy())
        self.paste_act = QAction("Paste", self, shortcut=QKeySequence.StandardKey.Paste,
                                 triggered=lambda: self._current() and self._current().paste())
        self.delete_act = QAction("Delete", self, shortcut=QKeySequence(Qt.Key.Key_Delete), triggered=self.edit_delete)
        self.select_all_act = QAction("Select All", self, shortcut=QKeySequence.StandardKey.SelectAll,
                                      triggered=lambda: self._current() and self._current().selectAll())
        self.find_act = QAction("Find", self, shortcut=QKeySequence.StandardKey.Find, triggered=self.edit_find)
        self.find_next_act = QAction("Find Next", self, shortcut=QKeySequence("F3"), triggered=lambda: self._find_again(True))
        self.find_prev_act = QAction("Find Previous", self, shortcut=QKeySequence("Shift+F3"), triggered=lambda: self._find_again(False))
        self.replace_act = QAction("Replace", self, shortcut=QKeySequence("Ctrl+H"), triggered=self.edit_replace)

        # Highlight mgmt
        self.clear_search_highlight_act = QAction("Clear Search Highlight", self,
                                                  shortcut=QKeySequence("Ctrl+Shift+K"),
                                                  triggered=self.clear_search_highlight)
        self.clear_all_highlights_act = QAction("Clear All Highlights", self,
                                                shortcut=QKeySequence("Ctrl+Alt+K"),
                                                triggered=self.clear_all_highlights)

        # Move Tab - Fixed shortcuts
        self.move_tab_left_act = QAction("Move Tab Left", self, shortcut=QKeySequence("Ctrl+Shift+,"),
                                         triggered=self.move_tab_left)
        self.move_tab_right_act = QAction("Move Tab Right", self, shortcut=QKeySequence("Ctrl+Shift+."),
                                          triggered=self.move_tab_right)

        # Format / View
        self.word_wrap_act = QAction("Word Wrap", self, checkable=True, triggered=self.format_toggle_wrap)
        self.word_wrap_act.setChecked(self.word_wrap_on)
        self.font_act = QAction("Font...", self, triggered=self.format_font)
        
        # Zoom actions
        self.zoom_in_act = QAction("Zoom In", self, shortcut=QKeySequence.StandardKey.ZoomIn, triggered=self.zoom_in)
        self.zoom_out_act = QAction("Zoom Out", self, shortcut=QKeySequence.StandardKey.ZoomOut, triggered=self.zoom_out)
        
        # Dark mode action
        self.dark_mode_act = QAction("Dark Mode", self, checkable=True, triggered=self.toggle_dark_mode)
        self.dark_mode_act.setChecked(self.dark_mode)

        # Encoding actions
        self.encoding_group = QActionGroup(self)
        self.encoding_actions = {}
        for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'ascii', 'latin-1', 'cp1252']:
            display_name = 'UTF-8-BOM' if enc == 'utf-8-sig' else enc.upper()
            act = QAction(display_name, self, checkable=True, triggered=lambda _, e=enc: self.set_encoding(e))
            self.encoding_group.addAction(act)
            self.encoding_actions[enc] = act
        # Set the current encoding as checked
        if self.default_encoding in self.encoding_actions:
            self.encoding_actions[self.default_encoding].setChecked(True)
        else:
            self.encoding_actions['utf-8'].setChecked(True)
        
        # Reopen with encoding action
        self.reopen_encoding_act = QAction("Reopen with Encoding...", self, triggered=self.fix_garbled_text)
        self.fix_garbled_act = QAction("Fix Garbled Text (Try All Encodings)...", self, shortcut=QKeySequence("Ctrl+Shift+E"), triggered=self.fix_garbled_text)
        self.remove_artifacts_act = QAction("Remove Artifacts from Current File", self, triggered=self.remove_artifacts)

        # Help & Tools
        self.about_act = QAction("About", self, triggered=self.help_about)
        self.help_act = QAction("Help", self, triggered=self.help_user_guide)

        self.hash_md5_act = QAction("MD5", self, triggered=lambda: self.compute_hash('md5', False))
        self.hash_sha1_act = QAction("SHA-1", self, triggered=lambda: self.compute_hash('sha1', False))
        self.hash_sha256_act = QAction("SHA-256", self, triggered=lambda: self.compute_hash('sha256', False))
        self.hash_sha512_act = QAction("SHA-512", self, triggered=lambda: self.compute_hash('sha512', False))
        self.hash_file_md5_act = QAction("MD5", self, triggered=lambda: self.compute_hash('md5', True))
        self.hash_file_sha1_act = QAction("SHA-1", self, triggered=lambda: self.compute_hash('sha1', True))
        self.hash_file_sha256_act = QAction("SHA-256", self, triggered=lambda: self.compute_hash('sha256', True))
        self.hash_file_sha512_act = QAction("SHA-512", self, triggered=lambda: self.compute_hash('sha512', True))
        self.syntax_check_act = QAction("Syntax Check Current", self, shortcut=QKeySequence("Ctrl+Shift+Y"), triggered=self.syntax_check_current)
        self.run_console_act = QAction("Run Selected Tab in Console", self, shortcut=QKeySequence("Ctrl+Shift+R"), triggered=self.run_selected_in_console)
        self.encoding_diagnostics_act = QAction("🔍 Encoding Diagnostics", self, shortcut=QKeySequence("Ctrl+Shift+G"), triggered=self.tools_encoding_diagnostics)

        # Mode
        self.mode_group = QActionGroup(self)
        self.mode_actions = {}
        for mode in LANG_MODES:
            act = QAction(mode, self, checkable=True, triggered=lambda _, m=mode: self.set_code_mode(m))
            self.mode_group.addAction(act); self.mode_actions[mode] = act
        self.mode_actions['Plain Text'].setChecked(True)

        # Compare
        self.compare_toggle_act = QAction("Compare Mode", self, checkable=True, triggered=self.toggle_compare)
        self.compare_file_act = QAction("Compare…", self,
                                        shortcut=QKeySequence("Ctrl+Alt+D"),
                                        triggered=self.compare_with_file)
        self.compare_with_tab_act = QAction("Compare with open tab…", self,
                                           shortcut=QKeySequence("Ctrl+Shift+D"),
                                           triggered=self.compare_with_open_tab_picker)
        self.compare_run_act = QAction("Run Compare", self,
                                      shortcut=QKeySequence("F5"),
                                      triggered=self.run_compare)

        # Make all action shortcuts visible in context menus
        for act in (
            self.undo_act, self.redo_act, self.cut_act, self.copy_act, self.paste_act, self.delete_act, self.select_all_act,
            self.new_act, self.open_act, self.save_act, self.save_as_act, self.save_as_pdf_act, self.print_act, self.close_tab_act,
            self.find_act, self.find_next_act, self.find_prev_act, self.replace_act,
            self.clear_search_highlight_act, self.clear_all_highlights_act,
            self.move_tab_left_act, self.move_tab_right_act,
            self.syntax_check_act, self.run_console_act,
            self.compare_toggle_act, self.compare_file_act, self.compare_with_tab_act, self.compare_run_act,
            self.fix_garbled_act, self.zoom_in_act, self.zoom_out_act
        ):
            try: 
                act.setShortcutVisibleInContextMenu(True)
                # Also make shortcuts visible in menu bars
                act.setIconVisibleInMenu(False)  # Clean look
            except Exception: pass

    def _create_menus(self):
        if getattr(self, "_menus_built", False): return
        self._menus_built = True

        mb = self.menuBar()
        file_menu = mb.addMenu("File")
        file_menu.addAction(self.new_act); file_menu.addAction(self.open_act)
        file_menu.addAction(self.save_act); file_menu.addAction(self.save_as_act)
        file_menu.addAction(self.save_as_pdf_act); file_menu.addSeparator()
        file_menu.addAction(self.print_act); file_menu.addSeparator()
        file_menu.addAction(self.close_tab_act); file_menu.addSeparator(); file_menu.addAction(self.exit_act)

        edit_menu = mb.addMenu("Edit")
        edit_menu.addAction(self.undo_act); edit_menu.addAction(self.redo_act); edit_menu.addSeparator()
        for a in [self.cut_act, self.copy_act, self.paste_act, self.delete_act, self.select_all_act]: edit_menu.addAction(a)
        edit_menu.addSeparator()
        for a in [self.find_act, self.find_next_act, self.find_prev_act, self.replace_act]: edit_menu.addAction(a)
        edit_menu.addSeparator()
        edit_menu.addAction(self.clear_all_highlights_act)
        edit_menu.addSeparator()
        edit_menu.addAction(self.move_tab_left_act)
        edit_menu.addAction(self.move_tab_right_act)

        fmt_menu = mb.addMenu("Format"); fmt_menu.addAction(self.word_wrap_act); fmt_menu.addAction(self.font_act)

        # Encoding menu - placed after Format
        enc_menu = mb.addMenu("Encoding")
        for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'ascii', 'latin-1', 'cp1252']:
            enc_menu.addAction(self.encoding_actions[enc])
        enc_menu.addSeparator()
        enc_menu.addAction(self.reopen_encoding_act)
        enc_menu.addAction(self.fix_garbled_act)
        enc_menu.addAction(self.encoding_diagnostics_act)

        view_menu = mb.addMenu("View")
        view_menu.addAction(self.zoom_in_act)
        view_menu.addAction(self.zoom_out_act)
        view_menu.addSeparator()
        view_menu.addAction(self.dark_mode_act)

        tools = mb.addMenu("Tools")
        
        # Hash Document submenu
        hash_doc_menu = tools.addMenu("Hash Current Document")
        hash_doc_menu.addAction(self.hash_md5_act)
        hash_doc_menu.addAction(self.hash_sha1_act)
        hash_doc_menu.addAction(self.hash_sha256_act)
        hash_doc_menu.addAction(self.hash_sha512_act)
        
        # Hash File submenu
        hash_file_menu = tools.addMenu("Hash File...")
        hash_file_menu.addAction(self.hash_file_md5_act)
        hash_file_menu.addAction(self.hash_file_sha1_act)
        hash_file_menu.addAction(self.hash_file_sha256_act)
        hash_file_menu.addAction(self.hash_file_sha512_act)
        
        tools.addSeparator()
        tools.addAction(self.syntax_check_act)
        tools.addAction(self.run_console_act)
        tools.addSeparator()
        tools.addAction(self.encoding_diagnostics_act)

        modes = mb.addMenu("Mode"); [modes.addAction(self.mode_actions[m]) for m in LANG_MODES]

        cmpm = mb.addMenu("Compare")
        cmpm.addAction(self.compare_file_act)
        cmpm.addAction(self.compare_with_tab_act)
        cmpm.addAction(self.compare_run_act)

        helpm = mb.addMenu("Help"); helpm.addAction(self.help_act); helpm.addAction(self.about_act)

    # ---------- Syntax helpers ----------
    def _syntax_check_python(self, text: str, filepath: str = None):
        """Use pyright and ruff for comprehensive Python syntax, type, and style checking"""
        issues = []
        
        # Check which tools are available
        def command_exists(command):
            try:
                if platform.system() == 'Windows':
                    result = subprocess.run(['where', command], capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    result = subprocess.run(['which', command], capture_output=True, text=True, timeout=2)
                return result.returncode == 0
            except:
                return False
        
        has_pyright = command_exists('pyright')
        has_ruff = command_exists('ruff')
        
        if not has_pyright and not has_ruff:
            QMessageBox.warning(self, "Linters Not Found", 
                "Neither pyright nor ruff is installed.\n\n"
                "Install them with:\n"
                "  pip install pyright ruff\n\n"
                "• Pyright: Type checking and error detection\n"
                "• Ruff: Fast linting and style checking")
            return issues
        
        # Save to temp file if no filepath provided
        temp_file = None
        try:
            if not filepath:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                    f.write(text)
                    temp_file = f.name
                    filepath = temp_file
            
            # Run pyright if available
            if has_pyright:
                try:
                    if platform.system() == 'Windows':
                        result = subprocess.run(
                            ['pyright', '--outputjson', filepath],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    else:
                        result = subprocess.run(
                            ['pyright', '--outputjson', filepath],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                    
                    # Parse JSON output
                    try:
                        import json
                        output = json.loads(result.stdout)
                        
                        # Extract diagnostics
                        if 'generalDiagnostics' in output:
                            for diag in output['generalDiagnostics']:
                                line = diag.get('range', {}).get('start', {}).get('line', 0) + 1  # pyright uses 0-based
                                col = diag.get('range', {}).get('start', {}).get('character', 0) + 1
                                severity = diag.get('severity', 'error')
                                message = diag.get('message', 'Unknown error')
                                rule = diag.get('rule', '')
                                
                                # Format message with tool, severity and rule
                                full_message = f"[pyright:{severity}] {message}"
                                if rule:
                                    full_message += f" ({rule})"
                                
                                issues.append((line, col, full_message))
                    
                    except json.JSONDecodeError:
                        pass  # Continue to ruff if pyright fails
                
                except subprocess.TimeoutExpired:
                    QMessageBox.warning(self, "Pyright Timeout", 
                        "Pyright took too long to analyze the file.")
                except Exception:
                    pass  # Continue to ruff if pyright fails
            
            # Run ruff if available
            if has_ruff:
                try:
                    if platform.system() == 'Windows':
                        result = subprocess.run(
                            ['ruff', 'check', '--output-format=json', filepath],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    else:
                        result = subprocess.run(
                            ['ruff', 'check', '--output-format=json', filepath],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                    
                    # Parse JSON output
                    try:
                        import json
                        output = json.loads(result.stdout)
                        
                        # Ruff returns a list of diagnostics
                        if isinstance(output, list):
                            for diag in output:
                                line = diag.get('location', {}).get('row', 1)
                                col = diag.get('location', {}).get('column', 1)
                                code = diag.get('code', '')
                                message = diag.get('message', 'Unknown error')
                                
                                # Format message with tool and rule code
                                full_message = f"[ruff:{code}] {message}"
                                
                                issues.append((line, col, full_message))
                    
                    except json.JSONDecodeError:
                        pass  # Silent fail for ruff parsing errors
                
                except subprocess.TimeoutExpired:
                    QMessageBox.warning(self, "Ruff Timeout", 
                        "Ruff took too long to analyze the file.")
                except Exception:
                    pass  # Silent fail for ruff errors
            
        except Exception as e:
            QMessageBox.critical(self, "Linter Error", 
                f"Error running linters:\n\n{str(e)}")
            return issues
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
        
        # Sort issues by line number, then column
        issues.sort(key=lambda x: (x[0], x[1]))
        
        return issues

    def _highlight_issue_lines(self, editor: QPlainTextEdit, issues, color=QColor(255, 120, 120, 70)):
        for ln, col, _ in issues:
            block = editor.document().findBlockByLineNumber(max(0, ln-1))
            if not block.isValid(): continue
            c = QTextCursor(block); c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat(); fmt.setBackground(color); c.setCharFormat(fmt)

    def _goto_line_in_editor(self, editor: QPlainTextEdit, line: int, col: int = 1):
        block = editor.document().findBlockByLineNumber(max(0, line - 1))
        if not block.isValid(): return
        cursor = QTextCursor(block)
        for _ in range(max(1, col) - 1):
            cursor.movePosition(QTextCursor.MoveOperation.Right)
        editor.setTextCursor(cursor); editor.centerCursor(); editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _goto_line(self, line: int, col: int = 1):
        ed = self._current()
        if ed: self._goto_line_in_editor(ed, line, col)

    def syntax_check_current(self):
        ed = self._current()
        if not ed:
            QMessageBox.information(self, "Syntax", "No document open."); return
        text = ed.toPlainText()
        mode = ed.mode().lower() if hasattr(ed, "mode") else "plain text"
        fname = os.path.basename(getattr(ed, 'path', '') or "Untitled")
        
        if mode == 'python':
            # Pass the file path if available, otherwise pyright will use a temp file
            filepath = getattr(ed, 'path', None)
            if filepath and not ed.document().isModified():
                # Use existing file
                issues = self._syntax_check_python(text, filepath)
            else:
                # Use temp file for unsaved/modified content
                issues = self._syntax_check_python(text, None)
        else:
            QMessageBox.information(self, "Syntax", f"Syntax checking is only available for Python.\n\nCurrent mode: {mode}")
            return
        
        if not issues:
            # Check which tools are available to show in success message
            def command_exists(command):
                try:
                    if platform.system() == 'Windows':
                        result = subprocess.run(['where', command], capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        result = subprocess.run(['which', command], capture_output=True, text=True, timeout=2)
                    return result.returncode == 0
                except:
                    return False
            
            tools = []
            if command_exists('pyright'):
                tools.append('pyright')
            if command_exists('ruff'):
                tools.append('ruff')
            
            tools_str = ' and '.join(tools) if tools else 'linters'
            QMessageBox.information(self, "Syntax", f"✓ No issues detected in {fname}\n\nChecked with {tools_str}.")
        else:
            self._highlight_issue_lines(ed, issues)
            ln, col, _ = issues[0]
            self._goto_line_in_editor(ed, ln, col)
            self._show_issues_table(issues, fname)

    def run_selected_in_console(self):
        ed = self._current()
        if not ed:
            QMessageBox.information(self, "Run", "No document open.")
            return
        
        mode = ed.mode().lower() if hasattr(ed, "mode") else "plain text"
        code = ed.toPlainText()
        fname = os.path.basename(getattr(ed, 'path', '') or "Untitled")
        
        # Only support Python
        if mode != 'python':
            QMessageBox.information(self, "Run", 
                f"Only Python code can be run directly in console.\n\n"
                f"Current mode: {mode}\n\n"
                f"To run Python code, set the mode to Python from the Mode menu.")
            return
        
        # Check if Python is available and actually works (not just a Windows Store stub)
        def python_works(command):
            try:
                # Try to actually run Python with --version to verify it works
                kwargs = {'capture_output': True, 'text': True, 'timeout': 2}
                
                # On Windows, hide the console window
                if platform.system() == 'Windows':
                    kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                
                result = subprocess.run([command, '--version'], **kwargs)
                # Check if it succeeded and output contains "Python"
                return result.returncode == 0 and ('python' in result.stdout.lower() or 'python' in result.stderr.lower())
            except:
                return False
        
        # Try python3 first (preferred on modern systems), then fall back to python, then py launcher
        python_cmd = None
        if python_works('python3'):
            python_cmd = 'python3'
        elif python_works('python'):
            python_cmd = 'python'
        elif python_works('py'):  # Windows Python Launcher
            python_cmd = 'py'
        
        if not python_cmd:
            QMessageBox.warning(self, "Python Not Found", 
                "Python is not installed or not in PATH.\n\n"
                "Please install Python from python.org to run Python code.\n\n"
                "Note: The Windows Store Python stub is not sufficient.")
            return
        
        # Save to temp file if needed
        try:
            if getattr(ed, 'path', None) and not ed.document().isModified():
                filepath = os.path.abspath(ed.path)
            else:
                # Save to temp file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                    f.write(code)
                    filepath = os.path.abspath(f.name)
            
            # Remove any trailing slashes
            filepath = filepath.rstrip('/\\')
            
            # Determine OS and run in console
            system = platform.system()
            
            if system == 'Windows':
                # Windows - create a temporary batch file to avoid quoting issues
                # This handles paths with apostrophes and special characters
                with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as bat:
                    bat.write(f'@echo off\n')
                    bat.write(f'{python_cmd} "{filepath}"\n')
                    bat.write(f'pause\n')
                    bat_path = bat.name
                
                # Run the batch file
                subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/k', bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
                self.status.showMessage(f"Running {fname} in new console window...", 3000)
                
            elif system == 'Darwin':  # macOS
                # macOS - open in Terminal.app
                script = f'{python_cmd} "{filepath}"; echo; echo "Press any key to close..."; read -n 1'
                subprocess.Popen(['osascript', '-e', f'tell application "Terminal" to do script "{script}"'])
                self.status.showMessage(f"Running {fname} in Terminal...", 3000)
                
            else:  # Linux and others
                # Try common terminal emulators
                terminals = [
                    ['x-terminal-emulator', '-e'],
                    ['gnome-terminal', '--'],
                    ['konsole', '-e'],
                    ['xterm', '-e'],
                    ['xfce4-terminal', '-e']
                ]
                
                launched = False
                for term in terminals:
                    try:
                        bash_cmd = f'{python_cmd} "{filepath}"; echo; echo "Press Enter to close..."; read'
                        subprocess.Popen(term + ['bash', '-c', bash_cmd])
                        launched = True
                        self.status.showMessage(f"Running {fname} in terminal...", 3000)
                        break
                    except FileNotFoundError:
                        continue
                
                if not launched:
                    QMessageBox.warning(self, "Run", 
                        f"Could not find a terminal emulator.\n\n"
                        f"Please run this command manually:\n{python_cmd} \"{filepath}\"")
            
        except Exception as e:
            QMessageBox.critical(self, "Run Error", f"Error running code:\n\n{str(e)}")

    def _show_issues_table(self, issues, source_name: str):
        dlg = QDialog(self); dlg.setWindowTitle(f"Syntax Issues — {source_name}"); dlg.resize(780, 480)
        layout = QVBoxLayout(dlg)
        table = QTableWidget(dlg); layout.addWidget(table)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Line", "Column", "Message"])
        table.setRowCount(len(issues))
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        for r, (ln, col, msg) in enumerate(issues):
            table.setItem(r, 0, QTableWidgetItem(str(ln)))
            table.setItem(r, 1, QTableWidgetItem(str(col)))
            table.setItem(r, 2, QTableWidgetItem(str(msg)))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        btns = QHBoxLayout()
        copy_sel_btn = QPushButton("Copy Selected"); copy_all_btn = QPushButton("Copy All")
        goto_btn = QPushButton("Go To"); close_btn = QPushButton("Close")
        for b in (copy_sel_btn, copy_all_btn, goto_btn): btns.addWidget(b)
        btns.addStretch(1); btns.addWidget(close_btn); layout.addLayout(btns)
        def _selected_rows():
            sel = table.selectionModel().selectedRows()
            return [ix.row() for ix in sel] if sel else []
        def _copy_rows(rows):
            lines = ["Line\tColumn\tMessage"]
            for r in rows:
                l = table.item(r, 0).text() if table.item(r, 0) else ""
                c = table.item(r, 1).text() if table.item(r, 1) else ""
                m = table.item(r, 2).text() if table.item(r, 2) else ""
                lines.append(f"{l}\t{c}\t{m}")
            QApplication.clipboard().setText("\n".join(lines))
            self.status.showMessage(f"Copied {len(rows)} row(s) to clipboard", 2500)
        def _copy_selected():
            rows = _selected_rows()
            if not rows:
                cells = sorted(table.selectedIndexes(), key=lambda x: (x.row(), x.column()))
                rows = sorted({c.row() for c in cells})
            if rows: _copy_rows(rows)
        def _copy_all(): _copy_rows(list(range(table.rowCount())))
        def _goto_selected():
            rows = _selected_rows() or [table.currentRow()]
            if not rows: return
            r = rows[0]
            try:
                ln = int(table.item(r,0).text()); col = int(table.item(r,1).text())
            except Exception:
                ln, col = 1, 1
            dlg.accept(); self._goto_line(ln, col)
        copy_sel_btn.clicked.connect(_copy_selected)
        copy_all_btn.clicked.connect(_copy_all)
        goto_btn.clicked.connect(_goto_selected)
        close_btn.clicked.connect(dlg.reject)
        copy_action = QAction("Copy", dlg)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(_copy_selected)
        dlg.addAction(copy_action)
        table.cellDoubleClicked.connect(lambda _r, _c: _goto_selected())
        dlg.exec()

    # ---------- Encoding Diagnostics ----------
    def tools_encoding_diagnostics(self):
        """Analyze current file for encoding issues and offer automatic repair"""
        ed = self._current()
        if not ed:
            QMessageBox.information(self, "Encoding Diagnostics", "No document is open.")
            return
        
        # Get current file info
        fname = getattr(ed, 'file_path', None)
        if fname:
            display_name = Path(fname).name
        else:
            display_name = "Untitled"
        
        # Get text content
        text = ed.toPlainText()
        
        # Analyze for issues
        issues = []
        
        # Check for UTF-16 CRLF artifacts (਍ഀ)
        utf16_marker = '\u0a0d\u0d00'  # ਍ഀ
        if utf16_marker in text:
            count = text.count(utf16_marker)
            issues.append(('UTF-16 CRLF Artifact', f'Found {count} instances of ਍ഀ (UTF-16 line endings read as UTF-8)', count))
        
        # Check for null bytes
        null_count = text.count('\x00')
        if null_count > 0:
            issues.append(('Null Bytes', f'Found {null_count} null bytes (possible binary data)', null_count))
        
        # Check for mixed line endings
        crlf_count = text.count('\r\n')
        lf_only_count = text.count('\n') - crlf_count
        cr_only_count = text.count('\r') - crlf_count
        
        if sum([crlf_count > 0, lf_only_count > 0, cr_only_count > 0]) > 1:
            issues.append(('Mixed Line Endings', 
                         f'CRLF: {crlf_count}, LF: {lf_only_count}, CR: {cr_only_count}', 
                         crlf_count + cr_only_count))
        
        # Check for suspicious character sequences (encoding artifacts)
        suspicious = []
        for i, char in enumerate(text):
            code = ord(char)
            # Korean Hangul used as encoding artifacts
            if 0xAC00 <= code <= 0xD7AF:
                suspicious.append((char, hex(code), i))
            # Malayalam/Indic used as encoding artifacts  
            elif 0x0D00 <= code <= 0x0D7F or 0x0A00 <= code <= 0x0A7F:
                if char != utf16_marker[0] and char != utf16_marker[1]:  # Don't double-count
                    suspicious.append((char, hex(code), i))
        
        if suspicious and len(suspicious) < 200:  # Only report if not too many
            unique_chars = {s[1] for s in suspicious}
            issues.append(('Suspicious Characters', 
                         f'Found {len(suspicious)} characters that may be encoding artifacts at positions like {suspicious[0][2]}',
                         len(suspicious)))
        
        # Check for UTF-8 BOM
        if text.startswith('\ufeff'):
            issues.append(('UTF-8 BOM', 'File starts with byte order mark', 1))
        
        # Check for common mojibake patterns
        mojibake_patterns = [
            ('â€™', 'Smart apostrophe misencoded'),
            ('â€œ', 'Smart quote (open) misencoded'),
            ('â€', 'Smart quote (close) misencoded'),
            ('Ã©', 'Accented é misencoded'),
            ('Ã¨', 'Accented è misencoded'),
            ('Ã ', 'Accented à misencoded'),
        ]
        
        for pattern, desc in mojibake_patterns:
            if pattern in text:
                count = text.count(pattern)
                issues.append(('Mojibake', f'{desc}: {count} instances of "{pattern}"', count))
        
        # Display results
        if not issues:
            QMessageBox.information(self, "Encoding Diagnostics", 
                                  f"✓ No encoding issues detected in {display_name}")
            return
        
        # Show issues in a dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Encoding Issues — {display_name}")
        dlg.resize(700, 450)
        
        dlg.setStyleSheet("""
            QListWidget { border: 1px solid #ccc; font-size: 10pt; }
            QListWidget::item { padding: 10px; }
            QPushButton { padding: 8px 16px; border-radius: 4px; font-size: 10pt; }
            QLabel { padding: 8px; font-size: 11pt; }
        """)
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        
        # Header
        header = QLabel(f"<b>Found {len(issues)} encoding issue(s) in {display_name}</b>")
        layout.addWidget(header)
        
        # Issues list
        issues_list = QListWidget()
        for issue_type, description, count in issues:
            severity = "🔴" if count > 50 else "🟡" if count > 10 else "⚠️"
            item = QListWidgetItem(f"{severity} {issue_type}: {description}")
            issues_list.addItem(item)
        layout.addWidget(issues_list)
        
        # Info label
        info = QLabel("Click 'Attempt Auto-Repair' to automatically fix detected issues.")
        info.setStyleSheet("font-style: italic; color: #888;")
        layout.addWidget(info)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        repair_btn = QPushButton("🔧 Attempt Auto-Repair")
        repair_btn.setStyleSheet("font-weight: bold;")
        copy_btn = QPushButton("📋 Copy Report")
        close_btn = QPushButton("Close")
        
        btn_layout.addWidget(repair_btn)
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        def repair_issues():
            """Attempt to automatically repair detected issues"""
            original_text = ed.toPlainText()
            repaired_text = original_text
            repairs = []
            
            # Remove UTF-16 CRLF artifacts
            if '\u0a0d\u0d00' in repaired_text:
                count = repaired_text.count('\u0a0d\u0d00')
                repaired_text = repaired_text.replace('\u0a0d\u0d00', '')
                repairs.append(f'Removed {count} UTF-16 CRLF artifacts (਍ഀ)')
            
            # Remove UTF-8 BOM
            if repaired_text.startswith('\ufeff'):
                repaired_text = repaired_text[1:]
                repairs.append('Removed UTF-8 BOM')
            
            # Remove null bytes
            if '\x00' in repaired_text:
                count = repaired_text.count('\x00')
                repaired_text = repaired_text.replace('\x00', '')
                repairs.append(f'Removed {count} null bytes')
            
            # Normalize line endings to \n
            if '\r' in repaired_text:
                original_lines = repaired_text.count('\n') + repaired_text.count('\r')
                repaired_text = repaired_text.replace('\r\n', '\n').replace('\r', '\n')
                repairs.append(f'Normalized line endings to LF (Unix style)')
            
            # Fix common mojibake
            mojibake_fixes = [
                ('â€™', "'"),
                ('â€œ', '"'),
                ('â€', '"'),
                ('Ã©', 'é'),
                ('Ã¨', 'è'),
                ('Ã ', 'à'),
            ]
            for wrong, right in mojibake_fixes:
                if wrong in repaired_text:
                    count = repaired_text.count(wrong)
                    repaired_text = repaired_text.replace(wrong, right)
                    repairs.append(f'Fixed {count} mojibake: {wrong} → {right}')
            
            # Remove suspicious Korean/Indic characters (likely artifacts)
            suspicious_removed = 0
            cleaned = []
            for char in repaired_text:
                code = ord(char)
                # Keep most Korean if it looks like actual content, but remove isolated artifacts
                if 0xAC00 <= code <= 0xD7AF:
                    # Check if surrounded by ASCII - likely artifact
                    suspicious_removed += 1
                    continue
                cleaned.append(char)
            
            if suspicious_removed > 0 and suspicious_removed < 50:  # Only if reasonable amount
                repaired_text = ''.join(cleaned)
                repairs.append(f'Removed {suspicious_removed} suspicious characters (likely encoding artifacts)')
            
            if repaired_text != original_text:
                # Apply repairs
                cursor = ed.textCursor()
                cursor.beginEditBlock()
                cursor.select(QTextCursor.SelectionType.Document)
                cursor.removeSelectedText()
                cursor.insertText(repaired_text)
                cursor.endEditBlock()
                
                # Mark as modified
                ed.document().setModified(True)
                
                # Show success message
                msg_text = "✓ Repairs Applied Successfully\n\n" + "\n".join(f"  • {r}" for r in repairs)
                msg_text += f"\n\nOriginal: {len(original_text)} chars\nRepaired: {len(repaired_text)} chars"
                QMessageBox.information(dlg, "Repair Complete", msg_text)
                self.status.showMessage(f"Repaired {len(repairs)} encoding issue(s)", 4000)
                dlg.accept()
            else:
                QMessageBox.information(dlg, "No Repairs Applied", 
                                      "Could not automatically repair the detected issues.\n\n"
                                      "Manual intervention may be required, or the issues detected "
                                      "may not be automatically fixable.")
        
        def copy_report():
            """Copy issues report to clipboard"""
            report_lines = [
                f"ENCODING DIAGNOSTICS REPORT",
                f"File: {display_name}",
                "=" * 60,
                ""
            ]
            for issue_type, description, count in issues:
                severity = "CRITICAL" if count > 50 else "WARNING" if count > 10 else "INFO"
                report_lines.append(f"[{severity}] {issue_type}")
                report_lines.append(f"  {description}")
                report_lines.append("")
            
            report_lines.append("=" * 60)
            report_lines.append(f"Total issues: {len(issues)}")
            report = "\n".join(report_lines)
            QApplication.clipboard().setText(report)
            self.status.showMessage("Report copied to clipboard", 2000)
        
        repair_btn.clicked.connect(repair_issues)
        copy_btn.clicked.connect(copy_report)
        close_btn.clicked.connect(dlg.reject)
        
        # Double-click to show more details
        def show_details(item):
            idx = issues_list.row(item)
            if idx >= 0:
                issue_type, description, count = issues[idx]
                details = f"{issue_type}\n\n{description}\n\nOccurrences: {count}"
                QMessageBox.information(dlg, "Issue Details", details)
        
        issues_list.itemDoubleClicked.connect(show_details)
        
        dlg.exec()

    # ---------- Help ----------
    def help_about(self):
        txt = ("Editor of Death\n\n"
               "Death's Head Software\n\n"
               "All commands target the clicked tab. Compare is whitespace-sensitive with character-level highlights.\n")
        QMessageBox.about(self, "About", txt)
    def help_user_guide(self):
        guide = ("Editor of Death - User Guide\n\n"
                 "All commands target the clicked tab. Compare is whitespace-sensitive with character-level highlights.\n\n"
                 "Right-click or click inside a tab to make it the target for File/Edit/Compare actions.\n"
                 "Use Compare → Compare… or Compare with open tab…; the clicked tab is the base side.\n\n"
                 "Keyboard shortcuts: Ctrl+Shift+, (Move Tab Left), Ctrl+Shift+. (Move Tab Right)")
        QMessageBox.information(self, "Help", guide)


# ---------------- App entry ----------------
def main():
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtCore import QTimer
    
    app = QApplication(sys.argv)
    app.setApplicationName("Editor of Death")
    app.setOrganizationName("Death's Head Software")
    
    # Single instance handling
    server_name = "EditorOfDeath_SingleInstance_v2"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    
    # Try to connect to existing instance
    is_running = socket.waitForConnected(500)
    
    if is_running:
        # Another instance is already running, send files to it
        files_to_open = []
        
        # Collect all file arguments
        for arg in sys.argv[1:]:
            # Convert to absolute path
            abs_path = os.path.abspath(arg)
            # Check if it exists (could be a file that will be created)
            if os.path.exists(abs_path) or not os.path.dirname(abs_path) or os.path.isdir(os.path.dirname(abs_path)):
                files_to_open.append(abs_path)
        
        if files_to_open:
            # Send file paths to existing instance
            data = '\n'.join(files_to_open).encode('utf-8')
            socket.write(data)
            socket.flush()
            socket.waitForBytesWritten(2000)
        
        socket.disconnectFromServer()
        if socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            socket.waitForDisconnected(1000)
        return 0
    
    # This is the first/only instance
    server = QLocalServer()
    # Remove any stale server
    QLocalServer.removeServer(server_name)
    
    if not server.listen(server_name):
        # If we still can't create server, just continue anyway (fallback to multi-instance)
        pass
    
    splash, msgs = create_splash()
    if splash:
        splash.show()
        for m in msgs:
            splash.showMessage("\n\n\n\n\n\n\n" + m,
                               Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
                               QColor(255,255,255))
            app.processEvents(); time.sleep(1.35)  # 5.4 seconds total (4 messages × 1.35s)
    
    win = EditorMain()
    
    # Handle incoming connections from other instances
    def on_new_connection():
        client_socket = server.nextPendingConnection()
        if not client_socket:
            return
        
        def on_ready_read():
            try:
                data = client_socket.readAll().data().decode('utf-8')
                files = [f.strip() for f in data.strip().split('\n') if f.strip()]
                
                for fpath in files:
                    if os.path.isfile(fpath):
                        # Open existing file
                        win._open_in_tabs(win.left_tabs, fpath)
                    elif not os.path.exists(fpath):
                        # File doesn't exist yet - create new tab with this path
                        ed = win._new_tab(win.left_tabs, "")
                        ed.path = fpath
                        win._retitle(ed)
                
                # Bring window to front
                win.setWindowState(win.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
                win.raise_()
                win.activateWindow()
            except Exception as e:
                pass  # Silent fail for IPC errors
        
        client_socket.readyRead.connect(on_ready_read)
        
        # Keep socket alive until it disconnects
        def on_disconnected():
            client_socket.deleteLater()
        client_socket.disconnected.connect(on_disconnected)
    
    server.newConnection.connect(on_new_connection)
    
    # Open files from command line for first instance
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            abs_path = os.path.abspath(arg)
            if os.path.isfile(abs_path):
                win._open_in_tabs(win.left_tabs, abs_path)
            elif not os.path.exists(abs_path):
                # File doesn't exist yet - create new tab with this path
                ed = win._new_tab(win.left_tabs, "")
                ed.path = abs_path
                win._retitle(ed)
    
    win.show()
    if splash: splash.finish(win)
    return app.exec()

if __name__ == "__main__":
    main()
