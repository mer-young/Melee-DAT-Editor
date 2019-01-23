# -*- coding: utf-8 -*-
"""
Created on Fri Dec  7 20:22:08 2018

GUI code for the dat editor.

@author: rmn
"""

import os
import struct
import sys

from PyQt5.Qt import (Qt, QKeySequence, QStyle, QIntValidator, QAction,
                      QDoubleValidator, QIcon, QMenu, QFont, QSize, QPoint,
                      QSizePolicy, pyqtSignal, pyqtSlot, QEventLoop)

from PyQt5.QtWidgets import (QApplication, QWidget, QMainWindow, QGridLayout,
                             QLabel, QFrame, QFileDialog, QSpinBox,
                             QTabWidget, QDialog, QListWidget, QStackedWidget,
                             QComboBox, QListWidgetItem, QTableWidget,
                             QTableWidgetItem, QLineEdit, QHBoxLayout,
                             QPushButton, QFormLayout, QDoubleSpinBox,
                             QVBoxLayout, QMessageBox, QToolBar)

from datfiles import moveset_datfile
import script


__version__ = '0.1.2 Alpha'
RELEASE_DATE = '22 January 2018'

ABOUT_TEXT = f"""
Melee Dat Editor
Version {__version__} ({RELEASE_DATE})

A tool for modifying Super Smash Bros. Melee fighter data files.

Copyright 2019 Richard M. North
Released under the terms of the GNU General Public License v3
"""


hex_caps = True
compact_event_display = True


def hex_display(string, show_0x=True):
    case_fun = str.upper if hex_caps else str.lower
    return '0x'*bool(show_0x) + case_fun(string.replace('0x', ''))


# TODO: get rid of unnecessary assignment of widgets to instance attributes
# if that widget is never referenced outside of _init__

class MainWindow (QMainWindow):
    """Main Window for the application"""
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)

        self.last_open_directory = ''
        self.last_save_directory = ''

        self.setWindowTitle('Melee Dat Editor')
        self.setWindowIcon(QIcon('resources/icon-256.ico'))
#        self.statusBar().showMessage('')  # enable status bar
        self.setup_menus()

        self.setAcceptDrops(True)

        self.setFixedSize(825, 700)
        self.show()

    def setup_menus(self):
        menubar = self.menuBar()
        style = self.style()
        file_menu = menubar.addMenu('File')
        open_action = file_menu.addAction(
                style.standardIcon(QStyle.SP_DialogOpenButton),
                'Open PlXx.dat...')
        open_action.setShortcut(QKeySequence('Ctrl+O'))
        open_action.triggered.connect(self.open_file_dialog)
#        open_action.setStatusTip('Open a dat file')

        save_action = file_menu.addAction(
                style.standardIcon(QStyle.SP_DialogSaveButton),
                'Save')
        save_action.setShortcut(QKeySequence('Ctrl+S'))
        save_action.triggered.connect(self.save)

        saveas_action = file_menu.addAction(
                style.standardIcon(QStyle.SP_DialogSaveButton),
                'Save As...')
        saveas_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        saveas_action.triggered.connect(self.saveas)
        file_menu.addSeparator()

        reload_action = file_menu.addAction(
                style.standardIcon(QStyle.SP_BrowserReload),
                'Reload From Disk')
        reload_action.triggered.connect(self.reload)

        close_action = file_menu.addAction(
                style.standardIcon(QStyle.SP_DialogCloseButton),
                'Close'
                )
        close_action.triggered.connect(self.close_current)

        help_menu = menubar.addMenu('Help')
        about_action = help_menu.addAction(
                style.standardIcon(QStyle.SP_MessageBoxInformation),
                'About...'
                )
        about_action.triggered.connect(self.about)

    def open_file_dialog(self):
        """Spawn an open file dialog and open the selected dat file"""
        fname = QFileDialog.getOpenFileName(
                self,
                'Open Moveset File',
                self.last_open_directory,
                'Moveset dat files (*.dat);;All Files (*.*)'
                )[0]
        if fname:
            self.open_file(fname)

    def open_file(self, fname):
        # TODO: when DatEx is implemented, replace MoveSetDatFile
        # constructor with a factory that examines the file and returns
        # an instance of the correct class, standard vs ex (vs other?)
        # and probably also updates old ex versions to newer ones
        # if necessary
        try:
            e = MovesetDatEditor(fname, self.last_save_directory, self)
        except Exception:
            import traceback
            mbox = QMessageBox(self)
            mbox.setWindowTitle(self.windowTitle())
            mbox.setText(f"Error opening {fname}.\n\n"
                         + traceback.format_exc()
                         )
            mbox.exec_()
            return
        self.last_open_directory = os.path.dirname(fname)
        self.tabs.addTab(e, os.path.basename(fname))
        self.tabs.setCurrentWidget(e)

    def save(self):
        if self.current_editor():
            self.current_editor().save()

    def saveas(self):
        if self.current_editor():
            self.current_editor().saveas()

    def reload(self):
        if self.current_editor():
            self.current_editor().reload()

    def current_editor(self):
        return self.tabs.currentWidget()

    def close_tab(self, index):
        e = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if e:
            e.close()

    def close_current(self):
        self.close_tab(self.tabs.currentIndex())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            print('ignore')
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            fname = url.toLocalFile()
            if os.path.isfile(fname):
                self.open_file(fname)

    def about(self):
        mbox = QMessageBox(self)
        mbox.setText(ABOUT_TEXT)
        mbox.setWindowTitle(self.windowTitle())
        mbox.exec_()


class MovesetDatEditor (QWidget):
    def __init__(self, fname, save_directory='', owner=None):
        super().__init__()

        # reference to the main window because parent is overwritten by addTab
        self.owner = owner
        self.grid = QGridLayout(self)
        self.fname = fname

        self.editors_list = QListWidget(self)
        self.editors_list.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.editors_list.setFixedWidth(150)
        self.frame = QStackedWidget(self)
        self.frame.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.initialize()

        self.grid.addWidget(QLabel(self.f.title(), self), 0, 0)
        self.grid.addWidget(self.editors_list, 1, 0)
        self.grid.addWidget(self.frame, 1, 1)
        self.grid.setColumnStretch(1, 1)

    def save(self):
        """Save the opened file (over itself)"""
        self.f.save(self.fname)
        self.last_save_directory = os.path.dirname(self.fname)

    def saveas(self):
        """Spawn a save file dialog and save as the selected file name"""
        self.fname = QFileDialog.getSaveFileName(
                self,
                'Save Moveset File As',
                self.last_save_directory,
                'Moveset dat files (*.dat)'
                )[0]
        if self.fname:
            self.save()
            # Retitle the tab to reflect the new filename.
            # QTabWidget uses a QStackedWidget internally, and that is the
            # parent of each tab, so we need parent() twice.
            tabs = self.parent().parent()
            tabs.setTabText(tabs.indexOf(self), os.path.basename(self.fname))

    def close(self):
        self.f.close()
        self.deleteLater()

    def reload(self):
        """Reload same file from disk"""
        while self.editors_list.count() > 0:
            w = self.editors_list.takeItem(0)
            del w
        while self.frame.count() > 0:
            w = self.frame.currentWidget()
            self.frame.removeWidget(w)
            w.deleteLater()
        self.f.close()
        self.initialize()

    def initialize(self):
        self.f = moveset_datfile(self.fname)
        self.setup_stacked_frame()

    @property
    def last_save_directory(self):
        return self.owner.last_save_directory

    @last_save_directory.setter
    def last_save_directory(self, val):
        self.owner.last_save_directory = val

    def setup_stacked_frame(self):
        self.script_widget = ScriptEditor(self.f)
        self.frame.addWidget(self.script_widget)

        self.common_attributes_widget = AttributeEditor(
                'Common Attributes',
                self.f.common_attributes_table
                )
        self.frame.addWidget(self.common_attributes_widget)

        self.unique_attributes_widget = AttributeEditor(
                'Unique Attributes',
                self.f.unique_attributes_table
                )
        self.frame.addWidget(self.unique_attributes_widget)

        self.hurtboxes_widget = HurtboxEditor(
                self.f.hurtbox_header,
                self.f.hurtbox_table
                )
        self.frame.addWidget(self.hurtboxes_widget)

        self.ledgegrab_editor = AttributeEditor(
                'Ledge Grab Box',
                self.f.ledge_grab_data
                )
        self.frame.addWidget(self.ledgegrab_editor)

        for i in range(self.frame.count()):
            new = QListWidgetItem(self.frame.widget(i).display_name)
            self.editors_list.addItem(new)
            self.editors_list.currentRowChanged.connect(
                    self.frame.setCurrentIndex
                    )
        self.editors_list.setCurrentRow(0)


class ScriptEditor (QWidget):
    display_name = 'Script Editor'

    def __init__(self, datfile):
        super().__init__()
        self.grid = QGridLayout(self)
        self.f = datfile

        self.dropdown = QComboBox(self)
        self.populate_dropdown()
        self.grid.addWidget(self.dropdown, 0, 0)

        self.location_display = QLineEdit(self)
        self.grid.addWidget(self.location_display, 0, 1)
        self.location_display.setReadOnly(True)

        self.event_list = self.EventList(self)
        self.event_list.follow_clicked.connect(self.open_location)
        self.grid.addWidget(self.event_list, 1, 0, 1, 2)

        self.toolbar = QToolBar(self)
        self.toolbar.setOrientation(Qt.Vertical)
        self.toolbar.addAction(self.event_list.move_up)
        self.toolbar.addAction(self.event_list.move_down)
        self.toolbar.addAction(self.event_list.new)
        self.toolbar.addAction(self.event_list.delete)
        self.grid.addWidget(self.toolbar, 1, 2)

        self.apply_button = QPushButton('Apply', self)
        self.apply_button.pressed.connect(self.apply)
        self.grid.addWidget(self.apply_button, 2, 0, 1, 2)

        self.dropdown.currentIndexChanged.connect(
                lambda index: self.location_display.setText(
                        '' if self.dropdown.currentData() is None
                        else hex(self.dropdown.currentData())
                        )
                )

        self.location_display.textChanged.connect(self.load_script_from)

        self.dropdown.setCurrentIndex(1)

    def populate_dropdown(self):
        self.dropdown.clear()
        for i, sa in self.f.iter_subactions():
            name = hex(i) + ': ' + self.f.subaction_short_name(i)
            self.dropdown.addItem(name,
                                  self.f.pointer(sa.script_pointer)
                                  )
        for offset in self.f.find_subroutines():
            if self.dropdown.findData(offset) == -1:
                name = 'Script at ' + hex(offset)
                self.dropdown.addItem(name, offset)

    def open_location(self, offset):
        offset = self.f.pointer(offset)
        index = self.dropdown.findData(offset)
        if index != -1:
            self.dropdown.setCurrentIndex(index)

    def load_script_from(self, offset_hex_text):
        self.event_list.clear()
        if not offset_hex_text:
            return
        offset = int(offset_hex_text, base=16)
        self.event_list.start_offset = offset
        for ev, offset in script.iter_script(self.f.script_at(offset), offset):
            self.event_list.add_event(ev, offset)

    def apply(self):
        self.f.replace_script_at(self.event_list.start_offset,
                                 self.event_list.get_script())
        pos = self.dropdown.currentIndex()
        self.populate_dropdown()
        self.dropdown.setCurrentIndex(pos)

    class EventList (QListWidget):
        follow_clicked = pyqtSignal(int)
        event_role = Qt.UserRole
        offset_role = Qt.UserRole + 1
        NOP = script.Event.from_hex('0xCC000000')

        def __init__(self, parent=None):
            super().__init__(parent)
            self.start_offset = None  # will be set by parent
            self.itemDoubleClicked.connect(
                    lambda item: self.popup_event_editor(self.row(item))
                    )

            self.setSelectionMode(self.ContiguousSelection)

            style = self.style()
            self.move_up = QAction(style.standardIcon(QStyle.SP_ArrowUp), 'Move Up', self)
            self.move_up.setShortcut(QKeySequence(Qt.Key_Minus))
            self.move_up.triggered.connect(lambda: self.shift(-1))
            self.addAction(self.move_up)

            self.move_down = QAction(style.standardIcon(QStyle.SP_ArrowDown), 'Move Down', self)
            self.move_down.setShortcut(QKeySequence(Qt.Key_Plus))
            self.move_down.triggered.connect(lambda: self.shift(+1))
            self.addAction(self.move_down)

            copy = QAction(self)
            copy.setShortcut(QKeySequence.Copy)
            copy.triggered.connect(self.copy)
            self.addAction(copy)

            paste = QAction(self)
            paste.setShortcut(QKeySequence.Paste)
            paste.triggered.connect(self.paste)
            self.addAction(paste)

            self.delete = QAction(style.standardIcon(QStyle.SP_TrashIcon), 'Delete', self)
            self.delete.setShortcut(QKeySequence.Delete)
            self.delete.triggered.connect(self.delete_selected)
            self.addAction(self.delete)

            self.new = QAction(style.standardIcon(QStyle.SP_FileIcon), 'Insert Event', self)
            self.new.triggered.connect(lambda: self.insert_event(self.currentRow(), self.NOP.copy()))
            self.addAction(self.new)

        def delete_selected(self):
            selected = sorted(self.selectedIndexes())
            if selected:
                self.setCurrentIndex(selected[0])
            row = self.currentIndex().row()
            for i in range(len(selected)):
                ev = self.takeItem(row)
                del ev

        def copy(self):
            s = ''
            for item in self.selectedItems():
                event_text = hex_display(hex(item.data(self.event_role)),
                                   show_0x=False
                                   )
                if len(event_text) % 2:
                    event_text = '0' + event_text
                s += event_text
            app.clipboard().setText(s)

        def paste(self):
            cb = app.clipboard()
            formats = cb.mimeData().formats()
            try:
                fmt_010 = r'application/x-qt-windows-mime;value="010 Editor Binary Data"'
                if fmt_010 in formats:
                    data = cb.mimeData().data(fmt_010)
                    # [:-2] because 010 appends \x00\x00
                    scr = script.script_from_bytes(data[:-2])
                    for ev in scr:
                        self.insert_event(max(self.currentRow(), 0), ev)
                # any other binary formats go here
                elif cb.text():
                    scr = script.script_from_hex_str(cb.text())
                    for ev in scr:
                        self.insert_event(max(self.currentRow(), 0), ev)
                self.selectionModel().clearSelection()
            except EOFError:
                mbox = QMessageBox(self)
                mbox.setText('Error interpreting pasted event data')
                mbox.exec_()

        def contextMenuEvent(self, e):
            row = self.currentRow()
            if self.item(row):
                event = self.item(row).data(Qt.UserRole)
                menu = QMenu(self)
                edit_action = menu.addAction(
                        self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                        'Edit'
                        )
                edit_action.triggered.connect(
                        lambda: self.popup_event_editor(row))
                menu.addAction(self.new)
#                insert_action = menu.addAction(
#                        self.style().standardIcon(QStyle.SP_FileIcon),
#                        'Insert Event'
#                        )
#                insert_action.triggered.connect(
#                        lambda: self.insert_event(self.currentRow(), self.NOP.copy())
#                        )
                if event.pointers:
                    follow_action = menu.addAction(
                            self.style().standardIcon(QStyle.SP_ArrowForward),
                            'Follow'
                            )
                    follow_action.triggered.connect(lambda: self.follow(row))
                menu.exec_(e.globalPos())

        def insert_event(self, pos, event):
            if self.item(pos) is None:
                offset = self.start_offset
            else:
                offset = self.item(pos).data(self.offset_role)
            self.insertItem(pos, self.item_from_event(event,offset))
            self.update_offsets()

        def popup_event_editor(self, row):
            ev = self.item(row).data(self.event_role)
            offset = self.item(row).data(self.offset_role)
            event_editor = EventEditor(ev, self)
            event_editor.applied.connect(
                    lambda ev: self.replace_event(row, ev, offset))
            event_editor.exec_()

        def replace_event(self, row, event, offset):
            self.insertItem(row + 1, self.item_from_event(event, offset))
            old = self.takeItem(row)
            del old

        def follow(self, row):
            target = self.item(row).data(self.event_role)['target']
            self.follow_clicked.emit(target)

        def add_event(self, event, offset):
            self.addItem(self.item_from_event(event, offset))

        @staticmethod
        def event_text(event, offset):
            if compact_event_display:
                return event.compact_str(offset=offset)
            else:
                return event.__str__(offset=offset)

        def item_from_event(self, event, offset):
            name = self.event_text(event, offset)
            new = QListWidgetItem(name)
            new.setData(self.event_role, event)
            new.setData(self.offset_role, offset)
            return new

        def get_script(self):
            return [self.item(row).data(self.event_role)
                    for row in range(self.count())]

        def update_offsets(self):
            offset = self.start_offset
            for row in range(self.count()):
                item = self.item(row)
                ev = item.data(self.event_role)
                item.setData(self.offset_role, offset)
                item.setText(self.event_text(ev, offset))
                offset += ev.length

        def shift(self, shift):
            # shift: 1 = down, -1 = up
            selected = sorted(self.selectedIndexes())
            if selected:
                if shift > 0:
                    # down
                    current = selected[-1]
                else:
                    # up
                    current = selected[0]
                self.setCurrentIndex(current)
            else:
                current = self.currentIndex()
            row = self.currentIndex().row()
            if not 0 <= row + shift < self.count():
                shift = 0
            for i in range(len(selected)):
                self.insertItem(row + (1-i)*shift, self.takeItem(row - i*shift))
                self.update_offsets()
            self.setCurrentRow(row + shift)
            self.selectionModel().clear()
            self.setCurrentIndex(
                    current.sibling(current.row() + shift, current.column()))
            for index in selected:
                self.selectionModel().select(
                        index.sibling(index.row() + shift, index.column()),
                        self.selectionModel().Select
                        )


class EventEditor (QDialog):
    applied = pyqtSignal(object)  # will send an Event instance

    def __init__(self, event, parent):
        super().__init__(parent)
        self.setWindowTitle('Event Editor')
        self.vbox = QVBoxLayout(self)
#        vbox.addWidget(QLabel(event.name))
        event_type_dropdown = QComboBox(self)
        for code, evtype in script.event_types.items():
            if code in ['length', 'default']:
                continue
            event_type_dropdown.addItem(
                    f'{evtype["name"]} ({hex(code)})',
                    code
                    )
        event_type_dropdown.setCurrentIndex(event_type_dropdown.findData(event.code))
        event_type_dropdown.currentIndexChanged.connect(
                lambda: self.change_type(event_type_dropdown.currentData())
                )
        self.vbox.addWidget(event_type_dropdown)

        form_widget = QWidget(self)
        self.vbox.addWidget(form_widget)
        self.form = QFormLayout(form_widget)
        self.event = event.copy()
        self.populate_form()

        buttons_widget = QWidget(self)
        buttons_hbox = QHBoxLayout(buttons_widget)
        ok_button = QPushButton('OK')
        ok_button.pressed.connect(lambda: self.apply(close=True))
        buttons_hbox.addWidget(ok_button)
        cancel_button = QPushButton('Cancel')
        cancel_button.pressed.connect(self.close)
        buttons_hbox.addWidget(cancel_button)
        apply_button = QPushButton('Apply')
        apply_button.pressed.connect(self.apply)
        buttons_hbox.addWidget(apply_button)
        self.vbox.addWidget(buttons_widget)

    def populate_form(self):
        self.field_entry = []
        for i, fd in enumerate(self.event.fields):
            print(fd['name'], fd['bits'], fd['type'])
            entry = self.field_editor(fd['bits'], fd['type'])
            entry.set_value(self.event[i])
            entry.editingFinished.connect(
                    lambda i=i, entry=entry: self.field_edited(i, entry.value())
                    )
            self.field_entry.append(entry)
            self.form.addRow(fd['name'], entry)

        self.raw_edit = self.field_editor([0, self.event.length*8 - 1], 'h')
        self.raw_edit.set_value(int(self.event))
        self.raw_edit.editingFinished.connect(self.raw_changed)
        self.form.addRow('Raw', self.raw_edit)

    def change_type(self, code):
        self.event = script.Event.blank(code)
        while self.form.count():
            self.form.removeRow(0)
        app.processEvents(QEventLoop.ExcludeUserInputEvents)
        self.resize(self.sizeHint());
        app.processEvents(QEventLoop.ExcludeUserInputEvents)
        self.resize(self.sizeHint());
        self.populate_form()
        app.processEvents(QEventLoop.ExcludeUserInputEvents)

    def raw_changed(self):
        self.event._data = self.raw_edit.value()
        self.update_fields()

    def field_edited(self, field, value):
        self.event[field] = value
        self.raw_edit.set_value(int(self.event))

    def update_fields(self):
        for i, entry in enumerate(self.field_entry):
            entry.set_value(self.event[i])

    def apply(self, close=False):
        if close:
            self.close()
        self.applied.emit(self.event)

    def field_editor(self, bit_range, type_str):
        if type_str == 'u':
            return self.IntFieldEntry(bit_range[1]-bit_range[0]+1, False, self)
        elif type_str == 's':
            return self.IntFieldEntry(bit_range[1]-bit_range[0]+1, True, self)
        elif type_str == 'h':
            byte_length = (bit_range[1] - bit_range[0] + 1)/8
            if not byte_length.is_integer():
                print(bit_range[1], bit_range[0])
                raise ValueError('Hex field length is not a multiple of 8 bits')
            return self.HexFieldEntry(byte_length, self)
        elif type_str == 'f':
            byte_length = (bit_range[1] - bit_range[0] + 1)/8
            if not byte_length == 4:
                raise ValueError('Float field length is not 32 bits')
            return self.FloatFieldEntry(False, self)
        elif type_str == 'f-upper':
            byte_length = (bit_range[1] - bit_range[0] + 1)/8
            if not byte_length == 2:
                raise ValueError('Upper-Half Float field length is not 16 bits')
            return self.FloatFieldEntry(True, self)

    class HexFieldEntry (QLineEdit):
        # Always an even number of bytes
        # should change to using a spinbox that displays hex instead of decimal
        value_changed = pyqtSignal(int)

        def __init__(self, byte_length, parent=None):
            super().__init__(parent)
            self.length = int(byte_length)
            case_char = '>' if hex_caps else '<'
            self.setInputMask(case_char + ' '.join(['HH']*self.length) + '')
            font = QFont('Hexedit-monospace')
            font.setStyleHint(QFont.Monospace)
            self.setFont(font)
            self.sizeHint = lambda: QSize(
                    self.fontMetrics().width(self.text() + '   '),
                    self.fontMetrics().height()*1.2,
                    )
            self.minimumSizeHint = self.sizeHint
            self.sizePolicy().setVerticalPolicy(QSizePolicy.Fixed)
            self.sizePolicy().setHorizontalPolicy(QSizePolicy.Minimum)
            self.updateGeometry()

            self.textChanged.connect(
                    lambda: self.value_changed.emit(self.value())
                    )

        def keyPressEvent(self, ev):
            if ev.key() in [Qt.Key_Shift, Qt.Key_Control, Qt.Key_Left,
                            Qt.Key_Right, Qt.Key_Up, Qt.Key_Down]:
                return super().keyPressEvent(ev)
            if self.selectedText():
                self.setCursorPosition(self.selectionStart())
                self.deselect()
            if ev.key() not in [Qt.Key_Backspace, Qt.Key_Delete]:
                super().keyPressEvent(ev)

        def value(self):
            return int(super().text().replace(' ', ''), base=16)

        def set_value(self, int_value):
            print(hex(int_value))
            self.setText(format(int_value, '0' + str(2*self.length) + 'x'))

    class IntFieldEntry (QSpinBox):
        # May be any number of bits wide
        def __init__(self, bit_width, signed, parent=None):
            super().__init__(parent)
            if signed:
                self.setMaximum(2**(bit_width-1) - 1)
                self.setMinimum(-2**(bit_width-1))
            else:
                self.setMaximum(2**bit_width - 1)
                self.setMinimum(0)

        def set_value(self, val):
            super().setValue(val)  # to match naming of other entry boxes

    class FloatFieldEntry (QDoubleSpinBox):
        # Always 32 bits
        Float = struct.Struct('>f')
        Int = struct.Struct('>I')
        raw_changed = pyqtSignal(int)

        def __init__(self, upper_only=False, parent=None):
            super().__init__(parent)
            self.setSingleStep(0.1)
            self.setDecimals(2)
            if upper_only:
                self.shift = 16
                self.setMaximum(self.from_raw(0x7F7F))
                self.setMinimum(self.from_raw(0xFF7F))
            else:
                self.shift = 0
                self.setMaximum(self.from_raw(0x7F7FFFFF))
                self.setMinimum(self.from_raw(0xFF7FFFFF))
            self.valueChanged.connect(
                    lambda: self.raw_changed.emit(self.value())
                    )

        def to_raw(self, float_val):
            return self.Int.unpack(self.Float.pack(float_val))[0] >> self.shift

        def from_raw(self, raw_val):
            return self.Float.unpack(self.Int.pack(raw_val << self.shift))[0]

        def value(self):
            # operates on raw value
            return self.to_raw(super().value())

        def set_value(self, val):
            # operates on raw value, not the decimal number it represents
            super().setValue(self.from_raw(val))


class AttributeEditor (QWidget):
    def __init__(self, display_name, attributes_table):
        super().__init__()
        self.display_name = display_name
        self.data = attributes_table
        self.grid = QGridLayout(self)
        self.table = self.AttributeTable(self)
        self.grid.addWidget(self.table, 0, 0)

        headings = ['Name', 'Value', 'Raw', 'Table Offset', 'File Offset',
                    'Type']
        self.table.setColumnCount(len(headings))
        for i, heading in enumerate(headings):
            self.table.setHorizontalHeaderItem(i, QTableWidgetItem(heading))

        for i, attrib in enumerate(self.data):
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(self.data.names[i])
            self.table.setItem(row, 0, name)
            value_entry = AttributeEntryCell(row, 1, type(attrib))
            value_entry.setText(self.format_value(attrib))
            value_entry.setFixedWidth(60)
            value_entry.edited.connect(self.update_value)
            value_entry.selected.connect(self.table.setCurrentCell)
            self.table.setCellWidget(row, 1, value_entry)
            raw = QTableWidgetItem(
                    hex_display(self.data.raw(i).hex())
                    )
            self.table.setItem(row, 2, raw)
            relative_offset = QTableWidgetItem(
                    hex_display(hex(self.data.get_relative_offset(i)))
                    )
            self.table.setItem(row, 3, relative_offset)
            file_offset = QTableWidgetItem(
                    hex_display(hex(self.data.get_offset(i)))
                    )
            self.table.setItem(row, 4, file_offset)
            kind = QTableWidgetItem(type(attrib).__name__)
            self.table.setItem(row, 5, kind)
            for item in (raw, relative_offset, file_offset, kind):
                item.setTextAlignment(Qt.AlignCenter)
            for item in (name, raw, relative_offset, file_offset, kind):
                item.setFlags(item.flags()
                              & ~Qt.ItemIsEditable
                              & ~Qt.ItemIsSelectable
                              )
        self.table.resizeColumnsToContents()

    def format_value(self, value):
        if isinstance(value, int):
            return f'{value:d}'
        if isinstance(value, float):
            return f'{value:.5f}'

    @pyqtSlot(int, int)
    def update_value(self, i, j):
        value_entry = self.table.cellWidget(i, j)
        self.data[i] = value_entry.type_(value_entry.text())
        value_entry.setText(self.format_value(self.data[i]))
        self.table.item(i, j+1).setText(hex_display(self.data.raw(i).hex()))

    class AttributeTable (QTableWidget):
        """Override Enter key behavior"""
        def keyPressEvent(self, ev):
            enter = ev.key() == Qt.Key_Enter or ev.key() == Qt.Key_Return
            shift = bool(ev.modifiers() & Qt.ShiftModifier)
            if ev.key() == Qt.Key_Backtab or (enter and shift):
                self.select_relative_row(-1)
            elif ev.key() == Qt.Key_Tab or enter:
                self.select_relative_row(+1)
            else:
                super().keyPressEvent(ev)

        def select_relative_row(self, relation):
            index = self.currentIndex()
            new_row = max(0, min(index.row()+relation, self.rowCount()-1))
            self.setCurrentCell(new_row, index.column())


class HurtboxEditor (QWidget):
    display_name = 'Hurtboxes'

    def __init__(self, hurtbox_header, hurtbox_table):
        super().__init__()
        self.grid = QGridLayout(self)
        self.hurtbox_header = hurtbox_header
        self.hurtbox_table = hurtbox_table
        self.table = self.Table()
        self.grid.addWidget(self.table, 1, 0, 1, 2)

        self.n_hurtboxes_entry = QSpinBox(self)
        self.n_hurtboxes_entry.setValue(self.hurtbox_header.n_hurtboxes)
        self.n_hurtboxes_entry.setRange(0, 15)
        self.n_hurtboxes_entry.valueChanged.connect(self.set_n_hurtboxes)
        w = QWidget(self)
        hbox = QHBoxLayout(w)
        hbox.addWidget(QLabel('Number of Hurtboxes: '))
        hbox.addWidget(self.n_hurtboxes_entry)
        self.grid.addWidget(w, 0, 0)

        self.make_table()

    def make_table(self):
        headers = ['Bone', '?', '?', 'x1', 'y1', 'z1', 'x2', 'y2',
                   'z2', 'scale', '']
        self.table.setColumnCount(len(headers))
        for i, h in enumerate(headers):
            self.table.setHorizontalHeaderItem(i, QTableWidgetItem(h))
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(self.hurtbox_header.n_hurtboxes)
        fmt = '.3f'
        for i, hurtbox in enumerate(self.hurtbox_table):
            bone = AttributeEntryCell(i, 0, type(hurtbox.bone), key=[i, 'bone'])
            bone.setText(str(hurtbox.bone))
            self.table.setCellWidget(i, 0, bone)

            u1 = AttributeEntryCell(i, 1, type(hurtbox.unk_int1), key=[i, 'unk_int1'])
            u1.setText(str(hurtbox.unk_int1))
            self.table.setCellWidget(i, 1, u1)

            u2 = AttributeEntryCell(i, 2, type(hurtbox.unk_int2), key=[i, 'unk_int2'])
            u2.setText(str(hurtbox.unk_int2))
            self.table.setCellWidget(i, 2, u2)

            x1 = AttributeEntryCell(i, 3, type(hurtbox.x1), key=[i, 'x1'])
            x1.setText(format(hurtbox.x1, fmt))
            self.table.setCellWidget(i, 3, x1)

            y1 = AttributeEntryCell(i, 4, type(hurtbox.y1), key=[i, 'y1'])
            y1.setText(format(hurtbox.y1, fmt))
            self.table.setCellWidget(i, 4, y1)

            z1 = AttributeEntryCell(i, 5, type(hurtbox.z1), key=[i, 'z1'])
            z1.setText(format(hurtbox.z1, fmt))
            self.table.setCellWidget(i, 5, z1)

            x2 = AttributeEntryCell(i, 6, type(hurtbox.x2), key=[i, 'x2'])
            x2.setText(format(hurtbox.x2, fmt))
            self.table.setCellWidget(i, 6, x2)

            y2 = AttributeEntryCell(i, 7, type(hurtbox.y2), key=[i, 'y2'])
            y2.setText(format(hurtbox.y2, fmt))
            self.table.setCellWidget(i, 7, y2)

            z2 = AttributeEntryCell(i, 8, type(hurtbox.z2), key=[i, 'z2'])
            z2.setText(format(hurtbox.z2, fmt))
            self.table.setCellWidget(i, 8, z2)

            scale = AttributeEntryCell(i, 9, type(hurtbox.scale), key=[i, 'scale'])
            scale.setText(format(hurtbox.scale, fmt))
            self.table.setCellWidget(i, 9, scale)

            close_button = self.CloseButton(i)
            close_button.close_pressed.connect(self.remove_hurtbox)
            self.table.setCellWidget(i, 10, close_button)

            for j in range(self.table.columnCount()-1):
                w = self.table.cellWidget(i, j)
                w.setFixedWidth(50)
                w.selected.connect(self.table.setCurrentCell)
                w.edited_key.connect(self.update_value)
        self.table.resizeColumnsToContents()

    def set_n_hurtboxes(self, n):
        prev_n = self.hurtbox_header.n_hurtboxes
        if n < prev_n:
            for _ in range(prev_n - n):
                del self.hurtbox_table[-1]
        elif n > prev_n:
            for _ in range(n - prev_n):
                self.hurtbox_table.append([0]*10)

        self.hurtbox_header.n_hurtboxes = n
        self.populate_table()

    def remove_hurtbox(self, index):
        del self.hurtbox_table[index]
        self.hurtbox_header.n_hurtboxes -= 1
        self.n_hurtboxes_entry.setValue(self.hurtbox_header.n_hurtboxes)
        self.populate_table()

    def update_value(self, key, value):
        self.hurtbox_table[key] = value
        self.populate_table()

    class CloseButton(QPushButton):
        close_pressed = pyqtSignal([int])

        def __init__(self, key):
            super().__init__()
            self.key_ = key
            self.pressed.connect(lambda: self.close_pressed.emit(self.key_))
#            self.setText('×')
#            self.setStyleSheet('QPushButton {color: red; font: 20px bold}')
            self.setIcon(
                    self.style().standardIcon(QStyle.SP_DockWidgetCloseButton)
                    )
            self.setFixedSize(25, 25)

    class Table (QTableWidget):
        """Override Enter key behavior"""
        def keyPressEvent(self, ev):
            enter = ev.key() == Qt.Key_Enter or ev.key() == Qt.Key_Return
            shift = bool(ev.modifiers() & Qt.ShiftModifier)
            if enter and shift:
                self.select_relative_row(-1)
            elif enter:
                self.select_relative_row(+1)
            elif ev.key() == Qt.Key_Tab:
                self.select_relative_column(+1)
            elif ev.key() == Qt.Key_Backtab:
                self.select_relative_column(-1)
            else:
                super().keyPressEvent(ev)

        def select_relative_row(self, relation):
            index = self.currentIndex()
            new_row = max(0,
                          min(index.row()+relation,
                              self.rowCount()-1
                              )
                          )
            self.setCurrentCell(new_row, index.column())

        def select_relative_column(self, relation):
            index = self.currentIndex()
            new_col = max(0,
                          min(index.column()+relation,
                              self.columnCount()-1
                              )
                          )
            self.setCurrentCell(index.row(), new_col)


class AttributeEntryCell (QLineEdit):
    selected = pyqtSignal([int, int])
    edited = pyqtSignal([int, int])
    edited_key = pyqtSignal([object, object])  # will be [list, self.type_]
    validators = {
            int: QIntValidator(),
            float: QDoubleValidator(),
            str: None,
            }

    def __init__(self, row, column, type_, key=None):
        super().__init__()
        self.row_ = row
        self.column_ = column
        self.type_ = type_
        self.key = key
        self.setValidator(self.validators[type_])
        self.setFrame(False)
        self.setAlignment(Qt.AlignCenter)
        self.editingFinished.connect(self.emit_edited)
        self.setAcceptDrops(True)

    def mousePressEvent(self, ev):
        self.select_all()

    def focusInEvent(self, ev):
        self.select_all()

    def select_all(self):
        self.selectAll()
        self.selected.emit(self.row_, self.column_)

    def emit_edited(self):
        self.edited.emit(self.row_, self.column_)
        self.edited_key.emit(self.key, self.type_(self.text()))

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and not event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        self.selectAll()
        self.insert(event.mimeData().text().strip())
        self.deselect()
        self.emit_edited()


if __name__ == '__main__':
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    main_window = MainWindow()

    # open any files passed from command line / drag and drop etc
    for arg in sys.argv[1:]:
        main_window.open_file(arg)

    sys.exit(app.exec_())
