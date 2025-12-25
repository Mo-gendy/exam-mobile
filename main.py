import flet as ft
import json
import random
import os
import base64

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
# We no longer hardcode a filename. The user will select it.
COLORS = {
    'primary': "blue700",
    'secondary': "grey500",
    'success': "green700",
    'error': "red700",
    'bg_card': "white",
    'bg_main': "blueGrey50",
    'text': "blueGrey900"
}

# -------------------------------------------------------------------------
# DATA MODELS
# -------------------------------------------------------------------------
class Question:
    def __init__(self, data):
        self.id = data.get("id")
        self.text = data.get("text", "")
        self.options = data.get("options", [])
        self.is_multichoice = data.get("is_multichoice", False)
        self.image_base64 = data.get("image_base64", None)
        
        self.user_answers = [] 
        self.is_locked = False 

    def check_answer(self):
        selected_indices = set(self.user_answers)
        correct_indices = {i for i, opt in enumerate(self.options) if opt['is_correct']}
        return selected_indices == correct_indices

    def get_correct_indices(self):
        return [i for i, opt in enumerate(self.options) if opt['is_correct']]

# -------------------------------------------------------------------------
# LOGIC ENGINE
# -------------------------------------------------------------------------
class ExamEngine:
    def __init__(self):
        self.all_questions = []
        self.active_questions = []
        self.current_idx = 0
        self.correct_count = 0
        self.answered_count = 0
        self.file_loaded = False

    def load_data_from_path(self, filepath):
        """Loads JSON data from a specific file path selected by user."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            self.all_questions = sorted([Question(item) for item in raw_data], key=lambda x: x.id)
            self.file_loaded = True
            return None
        except Exception as e:
            return f"Error loading file: {str(e)}"

    def start_exam(self, start_id, end_id, shuffle_q, shuffle_ans):
        if not self.file_loaded:
            return "No exam file loaded yet."

        self.correct_count = 0
        self.answered_count = 0
        
        filtered = [q for q in self.all_questions if start_id <= q.id <= end_id]
        if not filtered:
            return "No questions found in that ID range."

        for q in filtered:
            q.user_answers = []
            q.is_locked = False
            if shuffle_ans:
                random.shuffle(q.options)
        
        if shuffle_q:
            random.shuffle(filtered)
            
        self.active_questions = filtered
        self.current_idx = 0
        return None

    def get_current(self):
        if 0 <= self.current_idx < len(self.active_questions):
            return self.active_questions[self.current_idx]
        return None
    
    def update_stats(self, is_correct):
        self.answered_count += 1
        if is_correct:
            self.correct_count += 1

# -------------------------------------------------------------------------
# FLET GUI
# -------------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "Exam Engine Mobile"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLORS['bg_main']
    page.padding = 10
    page.scroll = ft.ScrollMode.ADAPTIVE

    engine = ExamEngine()

    # --- HELPERS ---
    def get_stats_text():
        total = len(engine.active_questions)
        pct = (engine.correct_count / engine.answered_count * 100) if engine.answered_count > 0 else 0
        return f"Progress: {engine.answered_count}/{total} | Score: {pct:.0f}%"

    def show_stats_dialog(e):
        dlg = ft.AlertDialog(
            title=ft.Text("Live Statistics"),
            content=ft.Text(f"Answered: {engine.answered_count}\nCorrect: {engine.correct_count}\nWrong: {engine.answered_count - engine.correct_count}"),
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def go_home(e=None):
        page.clean()
        page.add(startup_view)
        page.update()

    # --- STARTUP SCREEN ---
    
    # State controls for startup
    start_id_field = ft.TextField(label="Start ID", value="1", width=100, keyboard_type=ft.KeyboardType.NUMBER)
    end_id_field = ft.TextField(label="End ID", value="100", width=100, keyboard_type=ft.KeyboardType.NUMBER)
    chk_shuffle_q = ft.Checkbox(label="Shuffle Questions", value=False)
    chk_shuffle_a = ft.Checkbox(label="Shuffle Answers", value=False)
    
    file_status_text = ft.Text("No file loaded", color=COLORS['error'], italic=True)

    # --- FILE PICKER LOGIC ---
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            file_path = e.files[0].path
            if file_path:
                err = engine.load_data_from_path(file_path)
                if err:
                    file_status_text.value = f"Error: {err}"
                    file_status_text.color = COLORS['error']
                else:
                    file_status_text.value = f"Loaded: {e.files[0].name} ({len(engine.all_questions)} Qs)"
                    file_status_text.color = COLORS['success']
                    # Auto set end ID
                    if engine.all_questions:
                        end_id_field.value = str(engine.all_questions[-1].id)
                page.update()
        else:
            # User cancelled
            pass

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    def on_pick_click(e):
        # Trigger file picker
        file_picker.pick_files(allow_multiple=False, allowed_extensions=["json"])

    def on_start_click(e):
        if not engine.file_loaded:
            page.snack_bar = ft.SnackBar(ft.Text("Please load a JSON exam file first!"), bgcolor="red")
            page.snack_bar.open = True
            page.update()
            return

        try:
            s_id = int(start_id_field.value)
            e_id = int(end_id_field.value)
        except:
            page.snack_bar = ft.SnackBar(ft.Text("IDs must be numbers"), bgcolor="red")
            page.snack_bar.open = True
            page.update()
            return

        err = engine.start_exam(s_id, e_id, chk_shuffle_q.value, chk_shuffle_a.value)
        if err:
            page.snack_bar = ft.SnackBar(ft.Text(err), bgcolor="red")
            page.snack_bar.open = True
            page.update()
            return
            
        load_question_ui()

    startup_view = ft.Column([
        ft.Container(height=50),
        ft.Text("Exam Engine", size=30, weight=ft.FontWeight.BOLD, color=COLORS['primary']),
        ft.Text("Mobile Player", size=16, color=COLORS['secondary']),
        ft.Container(height=20),
        
        # File Selection Card
        ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column([
                    ft.Text("1. Load Data", weight=ft.FontWeight.BOLD, size=18),
                    ft.Text("Select the exam_data.json file from your device storage.", size=12, color="grey"),
                    ft.Container(height=10),
                    ft.ElevatedButton("Select JSON File", icon=ft.icons.UPLOAD_FILE, on_click=on_pick_click),
                    file_status_text
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )
        ),
        
        ft.Container(height=10),

        # Settings Card
        ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column([
                    ft.Text("2. Settings", weight=ft.FontWeight.BOLD, size=18),
                    ft.Row([start_id_field, end_id_field], alignment=ft.MainAxisAlignment.CENTER),
                    chk_shuffle_q,
                    chk_shuffle_a,
                    ft.Container(height=20),
                    ft.ElevatedButton("START EXAM", on_click=on_start_click, 
                                      bgcolor=COLORS['primary'], color="white", height=50, width=200)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )
        )
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)


    # --- QUESTION SCREEN ---
    
    def load_question_ui():
        page.clean()
        q = engine.get_current()
        
        if not q:
            # Show summary
            page.add(ft.Text("Exam Finished!", size=30), 
                     ft.Text(get_stats_text(), size=20),
                     ft.ElevatedButton("Restart", on_click=go_home))
            page.update()
            return

        # 1. Header
        header = ft.Row([
            ft.Text(f"Q {engine.current_idx + 1} / {len(engine.active_questions)}", weight=ft.FontWeight.BOLD),
            ft.IconButton(ft.icons.ANALYTICS, on_click=show_stats_dialog)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # 2. Question Text & Image
        content_col = [
            ft.Text(f"ID: {q.id}  •  {'Multiple Choice' if q.is_multichoice else 'Single Choice'}", color=COLORS['secondary'], size=12),
            ft.Text(q.text, size=16, weight=ft.FontWeight.W_500),
        ]
        
        # Image Handling
        if q.image_base64:
            img_control = ft.Image(
                src_base64=q.image_base64,
                fit=ft.ImageFit.CONTAIN,
                width=None, 
            )
            content_col.append(ft.Container(img_control, padding=10, border_radius=5))

        # 3. Options
        options_col = ft.Column(spacing=10)
        option_controls = [] 

        def on_option_click(e, idx):
            if q.is_locked: return
            
            if q.is_multichoice:
                # Immediate coloring for CLICKED item
                is_correct = q.options[idx]['is_correct']
                is_selected = option_controls[idx][1].value 
                
                # Sync logic
                q.user_answers = [i for i, (row, chk, txt) in enumerate(option_controls) if chk.value]

                text_widget = option_controls[idx][2]
                if is_selected:
                    text_widget.color = COLORS['success'] if is_correct else COLORS['error']
                    text_widget.weight = ft.FontWeight.BOLD
                else:
                    text_widget.color = COLORS['text']
                    text_widget.weight = ft.FontWeight.NORMAL
                text_widget.update()

            else:
                # Single choice
                q.user_answers = [idx]
                q.is_locked = True
                engine.update_stats(q.check_answer())
                apply_colors(q)
        
        for i, opt in enumerate(q.options):
            if q.is_multichoice:
                is_checked = i in q.user_answers
                control = ft.Checkbox(value=is_checked, on_change=lambda e, x=i: on_option_click(e, x))
            else:
                is_checked = i in q.user_answers
                control = ft.Checkbox(value=is_checked, on_change=lambda e, x=i: on_option_click(e, x), shape=ft.OutlinedBorder(corner_radius=100)) 

            txt = ft.Text(opt['text'], size=16, expand=True, color=COLORS['text'])
            
            if q.is_locked:
                control.disabled = True

            row = ft.Row([control, txt], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)
            option_controls.append((row, control, txt))
            options_col.controls.append(row)

        def apply_colors(question):
            correct_indices = question.get_correct_indices()
            for i, (row, ctrl, txt) in enumerate(option_controls):
                is_opt_correct = i in correct_indices
                is_selected = i in question.user_answers
                ctrl.disabled = True
                
                if is_selected:
                    if is_opt_correct:
                        txt.color = COLORS['success']
                        txt.weight = ft.FontWeight.BOLD
                    else:
                        txt.color = COLORS['error']
                        txt.weight = ft.FontWeight.BOLD
                elif question.is_locked:
                     if is_opt_correct:
                        txt.color = COLORS['success']
                        txt.weight = ft.FontWeight.BOLD
            page.update()

        if q.is_locked:
            apply_colors(q)

        # 4. Navigation
        def on_next(e):
            if not q.is_locked:
                q.is_locked = True
                if not q.user_answers:
                    engine.update_stats(False)
                else:
                    engine.update_stats(q.check_answer())
                apply_colors(q)
            else:
                engine.current_idx += 1
                load_question_ui()

        def on_prev(e):
            if engine.current_idx > 0:
                engine.current_idx -= 1
                load_question_ui()

        nav_row = ft.Row([
            ft.ElevatedButton("Previous", on_click=on_prev, disabled=(engine.current_idx == 0)),
            ft.ElevatedButton("Next" if not q.is_locked else "Continue >", on_click=on_next, bgcolor=COLORS['primary'], color="white")
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        page.add(
            ft.Container(padding=10, content=header),
            ft.Divider(),
            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=15,
                    bgcolor=COLORS['bg_card'],
                    content=ft.Column(content_col + [ft.Divider(), options_col])
                )
            ),
            ft.Container(height=20),
            nav_row
        )
        page.update()

    page.add(startup_view)

ft.app(target=main)
