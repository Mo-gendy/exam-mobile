import flet as ft
from docx import Document
import re
import random
import os
import base64
import io

# -------------------------------------------------------------------------
# CONFIG & ASSETS
# -------------------------------------------------------------------------
# Ensure this filename matches exactly what you put in the assets folder later
DEFAULT_FILENAME = "HCIA-datacom-EN.docx"

# Modern Color Palette (Using String Literals to avoid AttributeError)
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
    def __init__(self, q_id, text, options_data, is_multichoice, image_data=None):
        self.id = q_id
        self.text = text
        self.options = options_data 
        self.is_multichoice = is_multichoice
        self.image_data = image_data
        
        # State
        self.user_answers = [] 
        self.is_locked = False 
        self.is_correctly_answered = False

    def check_answer(self):
        selected_indices = set(self.user_answers)
        correct_indices = {i for i, opt in enumerate(self.options) if opt['is_correct']}
        return selected_indices == correct_indices

    def get_correct_indices(self):
        return [i for i, opt in enumerate(self.options) if opt['is_correct']]

# -------------------------------------------------------------------------
# PARSING LOGIC
# -------------------------------------------------------------------------
class ExamParser:
    @staticmethod
    def parse(filepath):
        # On mobile, we might need to handle absolute paths carefully
        if not os.path.exists(filepath):
            return [], f"File not found: {filepath}"

        try:
            document = Document(filepath)
        except Exception as e:
            return [], f"Error reading file: {str(e)}"

        questions = []
        current_q_id = None
        current_text = []
        current_options = {} 
        last_option_label = None 
        current_correct = []
        current_image_data = None

        re_q_start = re.compile(r'^\s*\*\*(\d+)\.\s*(.*)')
        re_option = re.compile(r'^\s*(?:□\s*)?([A-E])\.\s*(.*)')
        re_correct = re.compile(r'^\s*\*\*Correct Answer:\*\*\s*(.*)', re.IGNORECASE)

        def get_image_from_paragraph(paragraph, doc_part):
            for run in paragraph.runs:
                if 'blip' in run._element.xml:
                    xml_str = run._element.xml
                    if 'embed="' in xml_str:
                        start = xml_str.find('embed="') + 7
                        end = xml_str.find('"', start)
                        if start > 6 and end != -1:
                            rId = xml_str[start:end]
                            if rId in doc_part.related_parts:
                                return doc_part.related_parts[rId].blob
            return None

        def finalize_question():
            nonlocal current_q_id, current_text, current_options, current_correct, last_option_label, current_image_data
            if current_q_id and current_options and current_correct:
                sorted_keys = sorted(current_options.keys())
                options_data = []
                is_multi = len(current_correct) > 1
                
                for key in sorted_keys:
                    is_opt_correct = key in current_correct
                    options_data.append({
                        'text': current_options[key],
                        'is_correct': is_opt_correct,
                        'original_label': key
                    })
                
                q = Question(
                    q_id=int(current_q_id),
                    text="\n".join(current_text).strip(),
                    options_data=options_data,
                    is_multichoice=is_multi,
                    image_data=current_image_data
                )
                questions.append(q)

            current_q_id = None
            current_text = []
            current_options = {}
            last_option_label = None
            current_correct = []
            current_image_data = None

        for para in document.paragraphs:
            text = para.text.strip()
            img_blob = get_image_from_paragraph(para, document.part)
            
            if img_blob and current_q_id and not current_correct:
                current_image_data = img_blob

            if not text and not img_blob:
                continue

            match_q = re_q_start.match(text)
            if match_q:
                finalize_question()
                current_q_id = match_q.group(1)
                rest_of_text = match_q.group(2).strip("**")
                current_text = [rest_of_text] if rest_of_text else []
                continue

            match_a = re_correct.match(text)
            if match_a:
                raw = match_a.group(1)
                current_correct = [x.strip().upper() for x in re.split(r'[,\s]+', raw) if x.strip()]
                continue

            match_o = re_option.match(text)
            if match_o:
                label = match_o.group(1).upper()
                opt_text = match_o.group(2).strip()
                current_options[label] = opt_text
                last_option_label = label
                continue

            if current_q_id and not match_a and not match_o:
                if not current_options:
                    current_text.append(text)
                elif last_option_label:
                    current_options[last_option_label] += "\n" + text

        finalize_question()
        return questions, None

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

    def load_file(self):
        # Try finding the file in current dir or assets
        possible_paths = [DEFAULT_FILENAME, os.path.join("assets", DEFAULT_FILENAME)]
        final_path = None
        for p in possible_paths:
            if os.path.exists(p):
                final_path = p
                break
        
        if not final_path:
             return f"File '{DEFAULT_FILENAME}' not found."

        qs, error = ExamParser.parse(final_path)
        if error:
            return error
        self.all_questions = sorted(qs, key=lambda x: x.id)
        return None

    def start_exam(self, start_id, end_id, shuffle_q, shuffle_ans):
        self.correct_count = 0
        self.answered_count = 0
        
        filtered = [q for q in self.all_questions if start_id <= q.id <= end_id]
        if not filtered:
            return "No questions in range."

        for q in filtered:
            q.user_answers = []
            q.is_locked = False
            q.is_correctly_answered = False
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
    
    # Enable scroll to handle long questions on phones
    page.scroll = ft.ScrollMode.ADAPTIVE

    engine = ExamEngine()

    # --- UI COMPONENTS ---
    
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
    
    def on_start_click(e):
        err = engine.load_file()
        if err:
            page.snack_bar = ft.SnackBar(ft.Text(err), bgcolor="red")
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
        ft.Text("Mobile Edition", size=16, color=COLORS['secondary']),
        ft.Container(height=30),
        ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column([
                    ft.Text("Settings", weight=ft.FontWeight.BOLD),
                    ft.Row([start_id_field, end_id_field], alignment=ft.MainAxisAlignment.CENTER),
                    chk_shuffle_q,
                    chk_shuffle_a,
                    ft.Container(height=20),
                    ft.ElevatedButton("START EXAM", on_click=on_start_click, 
                                      bgcolor=COLORS['primary'], color="white", height=50, width=200)
                ])
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
        if q.image_data:
            b64_img = base64.b64encode(q.image_data).decode('utf-8')
            img_control = ft.Image(
                src_base64=b64_img,
                fit=ft.ImageFit.CONTAIN,
                # Width logic: Max width but handle small images nicely
                width=None, # Let it be natural or responsive
            )
            content_col.append(ft.Container(img_control, padding=10, border_radius=5))

        # 3. Options
        options_col = ft.Column(spacing=10)
        
        # We store references to controls to update colors later
        option_controls = [] 

        def on_option_click(e, idx):
            if q.is_locked: return
            
            # Logic
            if q.is_multichoice:
                # Toggle logic is handled by checkbox natively, we just sync state
                current_selected = []
                for i, (row_ctrl, check_ctrl, text_ctrl) in enumerate(option_controls):
                    if check_ctrl.value:
                        current_selected.append(i)
                q.user_answers = current_selected
                
                # Immediate coloring for CLICKED item
                is_correct = q.options[idx]['is_correct']
                is_selected = option_controls[idx][1].value # Checkbox state
                
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
            # We construct a custom Row to have full control over Text Color
            
            # Control type based on question
            if q.is_multichoice:
                # Checkbox
                is_checked = i in q.user_answers
                control = ft.Checkbox(value=is_checked, on_change=lambda e, x=i: on_option_click(e, x))
            else:
                # Radio simulation using Checkbox (or Radio)
                # Note: Flet RadioGroup is strict. Using Checkbox with logic is easier for custom layouts.
                # However, for UX, let's use a Checkbox that acts like a radio visually? 
                # Or just standard Checkbox but logic enforces single? Standard Checkbox is safest for custom coloring.
                is_checked = i in q.user_answers
                control = ft.Checkbox(value=is_checked, on_change=lambda e, x=i: on_option_click(e, x), shape=ft.OutlinedBorder(corner_radius=100)) # Round for radio look

            txt = ft.Text(opt['text'], size=16, expand=True, color=COLORS['text'])
            
            # Disable interaction if locked
            if q.is_locked:
                control.disabled = True

            row = ft.Row([control, txt], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)
            option_controls.append((row, control, txt))
            options_col.controls.append(row)

        # Coloring Helper
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

        # Re-apply colors if visiting back
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

        # Assemble Page
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

    # Initial Load
    page.add(startup_view)

ft.app(target=main)