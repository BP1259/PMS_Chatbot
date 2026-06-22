"""
pms_parser.py — Parser for both BP PMS guides in a single file

Builds chunks for two documents, both stored in pms_guide_chunks table
differentiated by doc_source:
  'employee'     — BP_PMS_Employee_Guideline.docx        (Steps 1-13)
  'line_manager' — Line_Manager_Guideline_Tutorial.docx  (Steps 1-12)

Employee guide:  one screenshot per step, 13 steps total
Line Manager guide: Step 1 has TWO screenshots (both render when Step 1 referenced)
"""

from __future__ import annotations
import base64
import zipfile
from dataclasses import dataclass, field
from typing import Optional

# ── Resource link ────────────────────────────────────────────────────────
PMS_RESOURCE_LINK = "https://drive.google.com/drive/folders/1aMOR9O57YafR6Jy9m5Kohiz_XG35v3h8"

RESOURCE_LINK_FOOTER = f"""

---
📹 **Video Tutorial & Supporting Documents**
If you'd like to watch a step-by-step video walkthrough or view supporting documents, click the link below:
🔗 {PMS_RESOURCE_LINK}"""


# ══════════════════════════════════════════════════════════════════════════
# EMPLOYEE GUIDE — image map & section map
# ══════════════════════════════════════════════════════════════════════════
STEP_IMAGE_MAP: dict[int, str] = {
    1:  "image1.jpeg",
    2:  "image2.jpeg",
    3:  "image3.jpeg",
    4:  "image4.jpeg",
    5:  "image5.png",
    6:  "image6.png",
    7:  "image7.jpeg",
    8:  "image8.jpeg",
    9:  "image9.jpeg",
    10: "image10.jpeg",
    11: "image11.jpeg",
    12: "image12.jpeg",
    13: "image13.jpeg",
}

STEP_SECTION_MAP: dict[int, str] = {
    1:  "Goals Input",
    2:  "Goals Input",
    3:  "Goals Input",
    4:  "Goals Input",
    5:  "Goals Input",
    6:  "Goals Input",
    7:  "Goals Input",
    8:  "Goals Input",
    9:  "Goals Input",
    10: "Self Evaluation",
    11: "Self Evaluation",
    12: "Self Evaluation",
    13: "Self Evaluation",
}

# ══════════════════════════════════════════════════════════════════════════
# LINE MANAGER GUIDE — image map
# All LM images are .jpg (employee guide uses .jpeg/.png)
# 01a / 01b = two screenshots for Step 1 (both step_number=1)
# login      = login screenshot in Section 3 of the doc
# ══════════════════════════════════════════════════════════════════════════
LM_IMAGE_MAP: dict[str, str] = {
    "login": "image1.jpg",
    "01a":   "image2.jpg",   # Step 1 – dashboard after login
    "01b":   "image3.jpg",   # Step 1 – clicking Others → Performance
    "02":    "image4.jpg",
    "03":    "image5.jpg",
    "04":    "image6.jpg",
    "05":    "image7.jpg",
    "06":    "image7.jpg",   # same file as Step 5 (doc authoring quirk)
    "07":    "image8.jpg",
    "08":    "image9.jpg",
    "09":    "image10.jpg",
    "10":    "image11.jpg",
    "11":    "image12.jpg",
    "12":    "image13.jpg",
}

LM_SECTION_RATING  = "Rating Subordinate Appraisals"
LM_SECTION_EDITING = "Editing a Completed Appraisal"


# ══════════════════════════════════════════════════════════════════════════
# SHARED DATACLASS
# ══════════════════════════════════════════════════════════════════════════
@dataclass
class PMSChunk:
    chunk_id:       str
    content:        str
    section:        str
    step_number:    int
    step_title:     str
    has_image:      bool
    image_filename: str
    image_data:     str        # base64-encoded bytes or ""
    chunk_type:     str        # step / overview / dos_donts / login_info
    doc_source:     str = "employee"  # 'employee' or 'line_manager'


# ══════════════════════════════════════════════════════════════════════════
# IMAGE READER
# ══════════════════════════════════════════════════════════════════════════
def _read_image_b64(docx_path: str, image_filename: str) -> str:
    """Extract a specific image from the docx ZIP and return it as base64."""
    with zipfile.ZipFile(docx_path, "r") as z:
        zip_path = f"word/media/{image_filename}"
        try:
            return base64.b64encode(z.read(zip_path)).decode("utf-8")
        except KeyError:
            print(f"  ⚠ Image not found in docx: {zip_path}")
            return ""


def _lm_img(docx_path: str, key: str) -> tuple[bool, str, str]:
    """Helper: return (has_image, filename, base64_data) for an LM image key."""
    filename = LM_IMAGE_MAP.get(key, "")
    if not filename:
        return False, "", ""
    data = _read_image_b64(docx_path, filename)
    return bool(data), filename, data


# ══════════════════════════════════════════════════════════════════════════
# EMPLOYEE GUIDE BUILDER  (unchanged from original — identical content)
# ══════════════════════════════════════════════════════════════════════════
def build_pms_chunks(docx_path: str) -> list[PMSChunk]:
    """
    Build all chunks from the BP PMS Employee Guideline docx.
    doc_source = 'employee'
    """
    chunks: list[PMSChunk] = []

    # ── Overview ──────────────────────────────────────────────────────────
    overview_text = """BP Performance Appraisal System — Overview

The BP Performance Appraisal System is a seven-step cycle managed through HRMS at https://bachaaparty.flowhcm.com

As an EMPLOYEE, you are responsible for two steps:
  • Step 2: Goals Input & Submission — enter your goals and submit for approval
  • Step 4: Self Evaluation & Form Submission — rate yourself on each goal and company values

Full cycle:
  Step 1 — Login: Access the system using your company credentials.
  Step 2 — Goals Input & Submission: Enter your goals and submit for approval.
  Step 3 — Goals Approval: HR reviews and approves submitted goals (Phase 1).
  Step 4 — Self Evaluation & Form Submission: Rate yourself on each goal and company values, add comments, and submit.
  Step 5 — Line Manager Appraisal & Rating: Line Manager / HOD conduct appraisal meeting, reviews self-evaluation.
  Step 6 — Reviews Auto Submitted to HR: Completed appraisals are automatically submitted to HR.
  Step 7 — Reports Available: Reports are accessible to employees and their line manager/HOD.

Important: Each step is time-bound. HR will communicate deadlines. Missing a deadline may delay your appraisal or increment review.

URL: https://bachaaparty.flowhcm.com
Browser: Use Chrome or Edge (desktop) for best experience.""" + RESOURCE_LINK_FOOTER

    chunks.append(PMSChunk(
        chunk_id="pms_overview", content=overview_text,
        section="General", step_number=0, step_title="System Overview",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="employee",
    ))

    # ── Login ─────────────────────────────────────────────────────────────
    login_text = """How to Log In to the BP Performance Appraisal System (HRMS)

URL: https://bachaaparty.flowhcm.com
Use a desktop browser — Chrome or Edge recommended.

Step-by-step:
1. Open https://bachaaparty.flowhcm.com in your browser.
2. Enter your Employee ID and password (provided by HR).
3. Click 'Login' or press Enter. You will be taken to your personal dashboard.
4. Verify your profile — check that your name, department, and line manager are correctly shown under "My Info" on the dashboard.

Important: If you cannot log in or your profile details are incorrect, contact HR immediately before proceeding.""" + RESOURCE_LINK_FOOTER

    chunks.append(PMSChunk(
        chunk_id="pms_login", content=login_text,
        section="Login", step_number=0, step_title="How to Log In",
        has_image=False, image_filename="", image_data="",
        chunk_type="login_info", doc_source="employee",
    ))

    # ── Steps 1–13 ───────────────────────────────────────────────────────
    step_definitions = [
        (1, "Navigate to Performance",
         """Step 1: Navigate to Performance

What to do:
From your dashboard, click "Others" in the top navigation bar, then select "Performance" from the dropdown menu.

This is how you access the performance management section of the HRMS system where you will enter your goals."""),

        (2, "Open Objective-KPI Request",
         """Step 2: Open Objective-KPI Request

What to do:
1. Click on "Evaluations" in the left sidebar.
2. In the Action column of your evaluation record, click the dropdown arrow.
3. Select "Objective-KPI Request" from the dropdown menu.

This opens the screen where you can begin adding your goals/KPIs for the appraisal cycle."""),

        (3, "Add a New KPI",
         """Step 3: Add a New KPI (Goal)

What to do:
The Performance Request screen will open, showing "Objective: Goals (80%)".
Click the "+New KPI" button to begin adding your first goal.

You will need to click this button for each goal you want to add. The total weightage of all your goals must add up to 100%."""),

        (4, "Record Your Individual Goal",
         """Step 4: Record Your Individual Goal

What to do:
The form will expand after clicking +New KPI. Fill in all four fields:
1. KPI Type — select the type of goal
2. KPI Title — write a clear, concise title for this goal
3. KPI Details — briefly explain the goal and how it will be measured
4. Weightage (%) — assign the percentage weightage for this specific KPI

Once all fields are filled, click "Add KPI" to save this entry.

Important: All your KPI weightages must total 100% across all goals."""),

        (5, "Add Remaining Goals",
         """Step 5: Add Remaining Goals

What to do:
Repeat the process for each remaining goal:
1. Click "+New KPI"
2. Fill in KPI Type, KPI Title, KPI Details, and Weightage (%)
3. Click "Add KPI" to save

Continue until all your goals for the appraisal cycle are entered.
Remember: All weightages must add up to 100% in total."""),

        (6, "Edit Goals Before Submission",
         """Step 6: Edit Goals Before Submission

What to do:
Before submitting, review all your recorded goals carefully.
- Click the yellow Edit icon next to any goal to modify it
- Click the red × button to remove a goal entirely

Once you are satisfied with all entries and the total weightage equals 100%, proceed to Step 7.

Warning: Once you submit (Step 7), you CANNOT edit your goals unless HR or your Line Manager sends them back for revision."""),

        (7, "Send Request for Approval",
         """Step 7: Send Request for Approval

What to do:
Once all goals are entered and reviewed, click the "Send Request" button at the bottom of the page.
This submits your goals to your Line Manager / HR for approval.

Important Warning: Once submitted, you cannot edit your goals unless HR or your Line Manager sends them back for revision. Do NOT submit until you are satisfied with ALL entries."""),

        (8, "Confirm Submission Status",
         """Step 8: Confirm Submission

What to check after clicking Send Request:
Your request will be generated and the status will change to "Pending Approval".
The KPI request will be sent to your Line Manager for review.

You will see the status update on screen confirming your goals have been submitted and are awaiting approval. No further action needed at this stage — wait for your Line Manager to approve."""),

        (9, "Notification of Approval",
         """Step 9: Notification of KPI Approval

What to look for:
After your Line Manager approves your KPI request, you will receive a notification.
Look for the Bell icon in the top navigation bar — click it to view the approval message.

Phase 1 (this year): Goals are reviewed and approved by HR.
Phase 2 (next year onwards): Line Managers will approve goals directly.

Once your goals are approved, wait for the self-evaluation window to open. HR will notify you when it is time to complete your self evaluation."""),

        (10, "Open Your Evaluation Form",
         """Step 10: Open Your Evaluation

What to do:
1. Go to Others → Performance → Evaluations (same navigation as before)
2. In the Action column for your evaluation record, click the dropdown arrow
3. Select "Evaluation" from the dropdown menu

This opens your self-evaluation form showing all your approved goals.

Note: This step is only available after your goals have been approved AND the self-evaluation window has been opened by HR."""),

        (11, "Rate Yourself on Each Goal",
         """Step 11: Rate Yourself on Each Goal

What to do:
The evaluation form will show your approved goals under "Objective #1: Goals (Weightage: 80%)".

For EACH KPI/goal:
1. Enter your self-assessment percentage in the input field (how well you achieved this goal)
2. Add a comment explaining your performance and supporting your rating

Be honest and objective. Add meaningful comments — do NOT leave comment boxes empty."""),

        (12, "Rate Yourself on Company Core Values",
         """Step 12: Rate Yourself on Company Core Values

What to do:
Scroll down to "Objective #2: Company Core Values (Weightage: 20%)".

For each Company Core Value:
1. Enter your rating percentage
2. If applicable, add a grace percentage
3. Add comments to support your rating on each value

Important: Do not inflate ratings without supporting comments. The Company Core Values section carries 20% of your total appraisal weightage."""),

        (13, "Submit Performance Evaluation",
         """Step 13: Submit Your Performance Evaluation

What to do:
1. Scroll to the bottom of the evaluation form
2. Review your self-weightage scores for both Goals (80%) and Company Core Values (20%)
3. Add any feedback for your manager in the "Feedback to Manager" text box
4. Click "Submit Performance Evaluation"

Final checklist before submitting:
✔ All goals rated with a percentage
✔ All comment boxes filled with meaningful comments
✔ Company Core Values rated and commented
✔ Feedback for manager added (optional but recommended)
✔ Total scores reviewed

Warning: Once submitted, the form is final. Do not submit without reviewing all entries."""),
    ]

    for step_num, step_title, instructions in step_definitions:
        image_file = STEP_IMAGE_MAP.get(step_num, "")
        section    = STEP_SECTION_MAP.get(step_num, "General")
        image_b64  = _read_image_b64(docx_path, image_file) if image_file else ""
        content    = (
            f"Section: {section}\n"
            f"Step {step_num}: {step_title}\n\n"
            f"{instructions}"
            f"{RESOURCE_LINK_FOOTER}"
        )
        chunks.append(PMSChunk(
            chunk_id=f"pms_step_{step_num:02d}", content=content,
            section=section, step_number=step_num, step_title=step_title,
            has_image=bool(image_b64), image_filename=image_file, image_data=image_b64,
            chunk_type="step", doc_source="employee",
        ))

    # ── Dos and Don'ts ────────────────────────────────────────────────────
    chunks.append(PMSChunk(
        chunk_id="pms_dos_donts",
        content="""BP Performance Appraisal System — Do's and Don'ts

DO:
✔ Submit goals before the deadline.
✔ Be honest and objective in your self-evaluation.
✔ Add meaningful comments to support your ratings.
✔ Verify all goals and ratings before submitting.
✔ Contact HR if you face any system issues.
✔ Check the Bell notification icon after submitting goals to confirm approval.
✔ Ensure all KPI weightages add up to 100%.

DON'T:
✘ Don't wait until the last day to submit.
✘ Don't inflate ratings without supporting comments.
✘ Don't leave comment boxes empty.
✘ Don't submit the form without reviewing all entries.
✘ Don't ignore system errors — report them to HR promptly.
✘ Don't submit goals until you are fully satisfied — you cannot edit after submission.

Contact HR for: login issues, incorrect profile details, system errors, or missed deadlines.""" + RESOURCE_LINK_FOOTER,
        section="General", step_number=0, step_title="Do's and Don'ts",
        has_image=False, image_filename="", image_data="",
        chunk_type="dos_donts", doc_source="employee",
    ))

    # ── Goals summary ─────────────────────────────────────────────────────
    chunks.append(PMSChunk(
        chunk_id="pms_goals_summary",
        content="""How to Enter Goals in the BP Performance Appraisal System — Complete Summary

Section: Goals Input & Submission (Steps 1–9)

Quick summary of all steps:
Step 1: From dashboard → click Others → Performance
Step 2: Evaluations (left sidebar) → Action dropdown → Objective-KPI Request
Step 3: Click "+New KPI" to start adding a goal
Step 4: Fill KPI Type, KPI Title, KPI Details, Weightage (%) → click Add KPI
Step 5: Repeat Steps 3–4 for ALL goals (all weightages must total 100%)
Step 6: Review your goals, edit (yellow icon) or delete (red ×) if needed
Step 7: Click "Send Request" to submit for approval
Step 8: Status changes to "Pending Approval" — wait for Line Manager/HR
Step 9: Bell notification confirms approval

Key rules:
- All weightage percentages must add up to 100%
- Once submitted, you CANNOT edit unless HR/Manager sends back for revision
- Meet the deadline communicated by HR or your appraisal may be delayed""" + RESOURCE_LINK_FOOTER,
        section="Goals Input", step_number=0, step_title="Goals Input Complete Guide",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="employee",
    ))

    # ── Self evaluation summary ───────────────────────────────────────────
    chunks.append(PMSChunk(
        chunk_id="pms_eval_summary",
        content="""How to Complete Your Self Evaluation — Complete Summary

Section: Self Evaluation & Form Submission (Steps 10–13)

Prerequisites: Goals must be approved AND HR must open the self-evaluation window.

Quick summary of all steps:
Step 10: Others → Performance → Evaluations → Action dropdown → Evaluation
Step 11: Rate yourself (%) on each goal under Objective #1: Goals (80% weightage) — add supporting comments for each
Step 12: Scroll down to Objective #2: Company Core Values (20% weightage) — rate yourself and add comments
Step 13: Review all scores → add Feedback to Manager (optional) → click "Submit Performance Evaluation"

Key rules:
- Goals section (Objective #1) = 80% of total appraisal
- Company Core Values (Objective #2) = 20% of total appraisal
- Every rating MUST have a supporting comment — do not leave comment boxes empty
- Do not inflate scores without evidence/justification
- Review everything before submitting — the form is final once submitted""" + RESOURCE_LINK_FOOTER,
        section="Self Evaluation", step_number=0, step_title="Self Evaluation Complete Guide",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="employee",
    ))

    print(f"  Employee step chunks   : {sum(1 for c in chunks if c.chunk_type == 'step')}")
    print(f"  Employee overview etc  : {sum(1 for c in chunks if c.chunk_type != 'step')}")
    print(f"  Employee with images   : {sum(1 for c in chunks if c.has_image)}")
    print(f"  Total employee chunks  : {len(chunks)}")
    return chunks


# ══════════════════════════════════════════════════════════════════════════
# LINE MANAGER GUIDE BUILDER
# ══════════════════════════════════════════════════════════════════════════
def build_lm_chunks(docx_path: str) -> list[PMSChunk]:
    """
    Build all chunks from the BP Line Manager Appraisal Tutorial docx.
    doc_source = 'line_manager'

    Step 1 has TWO screenshots (lm_step_01a + lm_step_01b).
    Both have step_number=1 so both images render when Step 1 is referenced.
    """
    chunks: list[PMSChunk] = []

    # ── Overview ──────────────────────────────────────────────────────────
    chunks.append(PMSChunk(
        chunk_id="lm_overview",
        content="""BP Performance Appraisal System — Line Manager Overview

As a Line Manager / HOD, you are responsible for:
  • Conducting subordinate appraisals (Steps 1–8): reviewing the employee's self-evaluation and entering your own ratings and comments.
  • Editing a Completed Appraisal (Steps 9–12): revising ratings or comments after submission if needed.

Full seven-step cycle (for context):
  Step 1 — Login
  Step 2 — Goals Input & Submission (employee)
  Step 3 — Goals Approval (HR)
  Step 4 — Self Evaluation & Form Submission (employee)
  Step 5 — Line Manager Appraisal & Rating → YOU conduct the appraisal, enter ratings and comments, and submit.
  Step 6 — Reviews Auto Submitted to HR
  Step 7 — Reports Available

System URL: https://bachaaparty.flowhcm.com
Browser: Use Chrome or Edge (desktop) for best experience.""" + RESOURCE_LINK_FOOTER,
        section="General", step_number=0, step_title="Line Manager Overview",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="line_manager",
    ))

    # ── Login (has screenshot: image1.jpg) ────────────────────────────────
    has_img, img_f, img_d = _lm_img(docx_path, "login")
    chunks.append(PMSChunk(
        chunk_id="lm_login",
        content="""How to Log In to the BP Performance Appraisal System (Line Manager)

URL: https://bachaaparty.flowhcm.com
Use a desktop browser — Chrome or Edge recommended.

Steps:
1. Open https://bachaaparty.flowhcm.com in your browser.
2. Enter your Employee ID and password (provided by HR).
3. Click 'Log In'. You will be taken to your personal dashboard.
4. Verify your profile — confirm your name, department, and role are correct.

If you cannot log in or your profile details are incorrect, contact HR immediately.""" + RESOURCE_LINK_FOOTER,
        section="Login", step_number=0, step_title="How to Log In",
        has_image=has_img, image_filename=img_f, image_data=img_d,
        chunk_type="login_info", doc_source="line_manager",
    ))

    # ── Steps 1–12 ───────────────────────────────────────────────────────
    # Step 1 — sub-chunk A (image2.jpg: dashboard view)
    has_img, img_f, img_d = _lm_img(docx_path, "01a")
    chunks.append(PMSChunk(
        chunk_id="lm_step_01a",
        content=f"""Section: {LM_SECTION_RATING}
Step 1: Navigate to Performance

What to do:
From your dashboard after login, click 'Others' in the top navigation bar.
Then select 'Performance' from the dropdown menu that appears.

This takes you to the Performance section where you can access your subordinates' evaluations.""" + RESOURCE_LINK_FOOTER,
        section=LM_SECTION_RATING, step_number=1, step_title="Navigate to Performance",
        has_image=has_img, image_filename=img_f, image_data=img_d,
        chunk_type="step", doc_source="line_manager",
    ))

    # Step 1 — sub-chunk B (image3.jpg: Others dropdown → Performance)
    has_img, img_f, img_d = _lm_img(docx_path, "01b")
    chunks.append(PMSChunk(
        chunk_id="lm_step_01b",
        content=f"""Section: {LM_SECTION_RATING}
Step 1 (continued): Select Performance from the Others Menu

After clicking 'Others' in the top navigation bar, a dropdown appears.
Select 'Performance' to open the Performance section.
You will then see the Performance menu in the left sidebar.""" + RESOURCE_LINK_FOOTER,
        section=LM_SECTION_RATING, step_number=1, step_title="Navigate to Performance",
        has_image=has_img, image_filename=img_f, image_data=img_d,
        chunk_type="step", doc_source="line_manager",
    ))

    # Remaining steps — one chunk each
    lm_step_definitions = [
        ("02", 2, "Open Evaluations & Identify Pending Records", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 2: Open Evaluations & Identify Pending Records

What to do:
1. Click on 'Evaluations' in the left sidebar under Performance.
2. The system shows your evaluations list with Status defaulting to 'Pending'.
3. Each row shows: employee name, department, review title, review dates, and status.
4. Look for records with Status: 'Line Manager Review' — these are waiting for your input."""),

        ("03", 3, "Open the Action Menu & Select Evaluation", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 3: Open the Action Menu & Select Evaluation

What to do:
1. In the Action column on the right, click the small dropdown arrow (▼) next to the record with Status: Line Manager Review.
2. A menu will appear.
3. Select 'Evaluation' to open the appraisal form for that employee.

Only records with Status 'Line Manager Review' are ready for you to rate."""),

        ("04", 4, "Review Form Header & Employee Details", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 4: Review Form Header & Employee Details

What you will see when the evaluation form opens:
The header shows: Review Title, Review Type (Line Manager Review), Employee Name, Department, Review Start & End Date, and the employee's own review notes.

Below the header the form begins with Objective #1: Goals (Weightage: 80%).
Before entering any ratings, confirm you have opened the correct employee's appraisal."""),

        ("05", 5, "Enter Your Rating for Each Goal", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 5: Enter Your Rating for Each Goal

What to do:
For each KPI under Objective #1: Goals (Weightage: 80%):
1. Review the KPI Title and Detail. The employee's self-rating is visible for reference.
2. Enter YOUR rating percentage in the 'Enter percentage here' field.
3. The score summary panel updates automatically in real time.
4. If applicable, enter a Grace Percentage in the second field.
5. Repeat for every KPI listed under Objective #1."""),

        ("06", 6, "Add a Comment for Each Goal", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 6: Add a Comment for Each Goal

Below each KPI's score entry there is a mandatory Comments field (marked with a red *).
Type a meaningful comment explaining and justifying the rating you have given.

Critical: Comments are MANDATORY — the form cannot be submitted if any comment box is left empty.
Write specific, individual comments for each KPI — do not copy-paste the same text."""),

        ("07", 7, "Rate Company Core Values (Objective #2)", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 7: Rate Company Core Values (Objective #2)

What to do:
1. Scroll down to Objective #2: Company Core Values (Weightage: 20%).
2. For each core value, enter your rating percentage.
3. If applicable, enter a Grace Percentage.
4. Add a comment in the Comments field for each core value.

Comments are required for core values too. The 20% weightage significantly affects the overall appraisal score."""),

        ("08", 8, "Review Summary & Submit", LM_SECTION_RATING,
         f"""Section: {LM_SECTION_RATING}
Step 8: Review Summary & Submit

What to do:
1. Scroll to the bottom of the evaluation form.
2. A summary table shows Self Weightage Score (employee's score) and Line Manager Weightage Score (your score) side by side.
3. Review both scores carefully.
4. Once satisfied, click 'Submit Performance Evaluation'.

After submitting the form moves to 'Completed' status. You can still edit it (see Steps 9–12) but check everything before clicking Submit."""),

        ("09", 9, "Go to Evaluations & Filter by Completed", LM_SECTION_EDITING,
         f"""Section: {LM_SECTION_EDITING}
Step 9: Go to Evaluations & Filter by Completed

Use this to find a submitted appraisal for editing:
1. Go to Others → Performance → Evaluations (same navigation as before).
2. The list defaults to 'Pending'. To find completed ones, change the Status filter.
3. Click the Status dropdown and select 'Completed'.
4. Click 'Apply'. The list now shows all completed appraisals you have submitted."""),

        ("10", 10, "Select 'Edit' from the Action Dropdown", LM_SECTION_EDITING,
         f"""Section: {LM_SECTION_EDITING}
Step 10: Select 'Edit' from the Action Dropdown

What to do:
1. In the Completed list, find the specific employee's appraisal you want to revise.
2. In the Action column, click the dropdown arrow (▼).
3. Select 'Edit' from the menu.
4. The evaluation form re-opens in editable mode with all previously entered data intact."""),

        ("11", 11, "Update Rating or Comment", LM_SECTION_EDITING,
         f"""Section: {LM_SECTION_EDITING}
Step 11: Update Rating or Comment

What to do:
1. The form re-opens with all previously entered data pre-filled.
2. Navigate to the specific KPI or Core Value you want to change.
3. Update the percentage rating — the score panel updates in real time.
4. Update the comment to reflect your revised assessment.

You can edit any KPI under Objective #1 or any value under Objective #2."""),

        ("12", 12, "Save Changes with 'Update Performance Evaluation'", LM_SECTION_EDITING,
         f"""Section: {LM_SECTION_EDITING}
Step 12: Save Changes with 'Update Performance Evaluation'

What to do:
1. After making all required changes, scroll to the bottom of the form.
2. Review the updated summary table showing revised final scores.
3. Click 'Update Performance Evaluation' to save your changes.

The form stays in Completed status with the updated scores/comments saved. HR will see the revised data."""),
    ]

    for img_key, step_num, step_title, section, instructions in lm_step_definitions:
        has_img, img_f, img_d = _lm_img(docx_path, img_key)
        chunks.append(PMSChunk(
            chunk_id=f"lm_step_{img_key}",
            content=instructions + RESOURCE_LINK_FOOTER,
            section=section, step_number=step_num, step_title=step_title,
            has_image=has_img, image_filename=img_f, image_data=img_d,
            chunk_type="step", doc_source="line_manager",
        ))

    # ── Summary chunks ────────────────────────────────────────────────────
    chunks.append(PMSChunk(
        chunk_id="lm_rate_summary",
        content=f"""How to Rate a Subordinate's Appraisal — Complete Summary (Line Manager)

Section: {LM_SECTION_RATING} (Steps 1–8)

Step 1: Dashboard → Others → Performance (two screenshots show the navigation)
Step 2: Evaluations (left sidebar) → find records with Status: Line Manager Review
Step 3: Action dropdown (▼) → select Evaluation
Step 4: Review the form header — confirm correct employee name and review details
Step 5: Enter your rating % for each KPI under Objective #1: Goals (80% weightage)
Step 6: Add a mandatory comment below each KPI — no comment box can be left empty
Step 7: Scroll to Objective #2: Core Values (20% weightage) — rate and comment each value
Step 8: Scroll to summary table → verify both scores → click Submit Performance Evaluation

Key rules:
- All comment fields are mandatory — you cannot submit without them
- Enter your OWN independent assessment, not just the employee's self-rating
- After submitting, the form moves to Completed (but can still be edited — see Steps 9–12)""" + RESOURCE_LINK_FOOTER,
        section=LM_SECTION_RATING, step_number=0, step_title="Rating Subordinates Complete Guide",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="line_manager",
    ))

    chunks.append(PMSChunk(
        chunk_id="lm_edit_summary",
        content=f"""How to Edit a Completed Appraisal — Complete Summary (Line Manager)

Section: {LM_SECTION_EDITING} (Steps 9–12)

Use this if you need to correct a rating or comment after already submitting.

Step 9:  Others → Performance → Evaluations → change Status filter to 'Completed' → Apply
Step 10: Find the employee's record → Action dropdown (▼) → select Edit
Step 11: Update the percentage rating and/or comment for the relevant KPI or Core Value
Step 12: Scroll to bottom → review revised summary scores → click Update Performance Evaluation

Key rules:
- You can only edit appraisals that YOU submitted (Status: Completed in your list)
- Changes are saved immediately on clicking Update
- HR will see the revised ratings""" + RESOURCE_LINK_FOOTER,
        section=LM_SECTION_EDITING, step_number=0, step_title="Edit Completed Appraisal Guide",
        has_image=False, image_filename="", image_data="",
        chunk_type="overview", doc_source="line_manager",
    ))

    chunks.append(PMSChunk(
        chunk_id="lm_dos_donts",
        content="""BP Performance Appraisal System — Line Manager Do's and Don'ts

DO:
✔ Complete all appraisals before the HR deadline.
✔ Review the employee's self-evaluation before entering your own rating.
✔ Enter meaningful, specific comments for every KPI and Core Value.
✔ Be fair and objective — base ratings on actual performance evidence.
✔ Review the summary table before clicking Submit.
✔ Contact HR if you encounter system issues or cannot access an evaluation.

DON'T:
✘ Don't leave any comment fields empty — the form will not submit.
✘ Don't copy-paste the same comment for every KPI.
✘ Don't simply mirror the employee's self-rating without independent assessment.
✘ Don't miss deadlines — delayed appraisals affect employee increments.
✘ Don't ignore system errors — report them to HR promptly.""" + RESOURCE_LINK_FOOTER,
        section="General", step_number=0, step_title="Do's and Don'ts",
        has_image=False, image_filename="", image_data="",
        chunk_type="dos_donts", doc_source="line_manager",
    ))

    print(f"  LM step chunks         : {sum(1 for c in chunks if c.chunk_type == 'step')}")
    print(f"  LM overview/other      : {sum(1 for c in chunks if c.chunk_type != 'step')}")
    print(f"  LM with images         : {sum(1 for c in chunks if c.has_image)}")
    print(f"  Total LM chunks        : {len(chunks)}")
    return chunks


# ══════════════════════════════════════════════════════════════════════════
# COMBINED BUILDER
# ══════════════════════════════════════════════════════════════════════════
def build_all_chunks(employee_docx: str, lm_docx: str) -> list[PMSChunk]:
    """Build chunks for both guides and return combined list."""
    print("\n🧩 Building Employee Guide chunks:")
    emp = build_pms_chunks(employee_docx)

    print("\n🧩 Building Line Manager Guide chunks:")
    lm  = build_lm_chunks(lm_docx)

    total = emp + lm
    print(f"\n  Grand total chunks     : {len(total)}")
    return total


# ══════════════════════════════════════════════════════════════════════════
# ANNUAL APPRAISAL GUIDELINES (2025-2026) — policy/reference doc, no images
# doc_source = 'guidelines'
# Source: Guidelines_Annual_Appraisal_2025-2026.docx (10 numbered sections,
# no tables, no inline images). Content is reproduced in full below, split
# into one chunk per logical sub-topic so each chunk stays focused, but the
# RAG pipeline always sends ALL guideline chunks together as one combined
# context (same "full guide, every call" pattern as the employee/LM guides
# in build_pms_chunks / build_lm_chunks) — so partial vs. full questions
# both just work without any separate retrieval logic.
# ══════════════════════════════════════════════════════════════════════════

def build_guidelines_chunks(docx_path: str | None = None) -> list[PMSChunk]:
    """
    Build chunks for the Annual Appraisal Guidelines 2025-2026.
    doc_source = 'guidelines'

    docx_path is accepted for interface consistency with build_pms_chunks /
    build_lm_chunks (and so ingest_pms.py's hash-tracking can watch the file
    for changes), but the content here is authored directly rather than
    parsed from the docx at runtime, since the source document is plain
    text with no images or tables to extract.
    """
    chunks: list[PMSChunk] = []

    def add(chunk_id: str, section: str, title: str, content: str, order: int):
        chunks.append(PMSChunk(
            chunk_id=chunk_id, content=content.strip(),
            section=section, step_number=order, step_title=title,
            has_image=False, image_filename="", image_data="",
            chunk_type="guideline_section", doc_source="guidelines",
        ))

    add(
        "guide_01_goals_self_eval", "Annual Goals", "Annual Goals — Self-Evaluation", """
Section 1: Annual Goals — Self-Evaluation

Against each goal, employees will evaluate themselves and provide details of their scoring:
- Review your annual goals set for the period July 2025 – June 2026.
- Evaluate your performance against each goal, considering achievements, challenges, and learnings.
- Keep in mind the entire year's progress, not just recent progress.
- Provide concrete examples, projects, and accomplishments to support your score.
- Assign a percentage score of 0–100% to rate your performance against each goal.
- Provide concise comments summarizing your accomplishments, challenges, and lessons learned for each goal.
""", 1)

    add(
        "guide_02_goals_grace_marks", "Annual Goals", "Scoring Above 100% — Grace Marks (Goals)", """
Section 1 (continued): Scoring Above 100% on Annual Goals

A score above 100% is only applicable in exceptional cases where performance has clearly exceeded the
set target, supported by strong facts, figures, and evidence. In such cases, grace marks of up to 50%
may be awarded, bringing the maximum possible score to 150%. Detailed comments and justification are
mandatory for any score above 100%, and HR will request a formal explanation accordingly.
""", 2)

    add(
        "guide_03_cotic_self_eval", "COTIC Values", "Bachaa Party Values (COTIC) — Self-Evaluation", """
Section 2: Bachaa Party Values (COTIC) — Self-Evaluation

Against each company value (COTIC), employees will evaluate themselves and assign scores:
- Assign a percentage score of 0–100% in the score column for each value.
- Provide details and comments justifying your score for each value.
""", 3)

    add(
        "guide_04_cotic_grace_marks", "COTIC Values", "Scoring Above 100% — Grace Marks (COTIC)", """
Section 2 (continued): Scoring Above 100% on COTIC Values

A score above 100% is only applicable in exceptional cases where an employee has demonstrated clearly
exceptional alignment with company values, supported by strong facts, figures, and evidence. In such
cases, grace marks of up to 50% may be awarded, bringing the maximum possible score to 150%. Detailed
comments and justification are mandatory for any score above 100%, and HR will request a formal
explanation accordingly.
""", 4)

    add(
        "guide_05_overall_score", "Overall Score", "Overall Final Score (Auto-Calculated)", """
Section 3: Overall Final Score (Auto-Calculated)

The overall score is automatically calculated by the FlowHCM system using a weighted average of 80%
for Goals and 20% for Values. After completing their self-evaluation, employees will submit the form
through the FlowHCM Appraisal System to their Line Manager / HOD.
""", 5)

    add(
        "guide_06_leadership_eval", "Leadership Evaluation", "Evaluation on Leadership & Team Management", """
Section 4: Evaluation on Leadership & Team Management

The appraiser should evaluate the Leadership & Team Management competency of Lead / Assistant Manager
above level staff. The appraiser evaluates the following points where applicable:
- Ability to translate departmental/functional goals and communicate respective goals to subordinates.
- Adopt different leadership styles to meet situational requirements.
- Help the team stay focused on major goals, remain accessible to team members, and motivate them.
- Demonstrate the ability to bring new strategic concepts.
- Anticipate issues affecting the department and present workable solutions.
- Encourage collaboration across functional/departmental boundaries and discourage working in silos.
- Any other relevant point related to leadership & team management.

Note: this section applies only to Lead / Assistant Manager level staff and above — not to all employees.
""", 6)

    add(
        "guide_07_lm_hod_eval", "Manager Evaluation", "Line Manager / HOD Evaluation", """
Section 5: Line Manager / HOD Evaluation

Line Managers and HODs will assign a percentage score to each employee against each goal and value.
- If the manager's score differs from the employee's score, the manager must enter detailed comments
  explaining the difference.
- Ensure transparent scoring and consider the entire year's performance, not just recent performance.
- Provide concrete, work-related examples for easy understanding and learning of staff.
- The FlowHCM system provides the weighted average score based on 80% Goals and 20% Values.
""", 7)

    add(
        "guide_08_ace_dialogue", "Appraisal Dialogue", "Appraisal Dialogue (ACE)", """
Section 6: Appraisal Dialogue (ACE)

After completing the evaluation in FlowHCM, the Line Manager / HOD must conduct an appraisal discussion
with each team member. This is a critical activity. The following three points must be covered:

- Appreciation: Acknowledge and appreciate the employee's strengths and good performance.
- Coach & Counsel: Identify improvement areas, counsel, and coach employees so they can improve. Be as
  objective as possible — use concrete, work-related examples.
- Encourage: End the discussion with encouragement, motivating the employee to work hard and improve
  on the discussed points.

ACE stands for Appreciation, Coach & Counsel, Encourage.
""", 8)

    add(
        "guide_09_next_year_goals", "Next Year Goals", "Next Year Goals Discussion", """
Section 7: Next Year Goals Discussion

During the appraisal meeting, the Line Manager will collaborate with staff to set SMART Goals for
FY 2026–2027 as per the new goals guidelines. The Line Manager will:
- Ensure staff understand their role in achieving department and company goals.
- Encourage staff to take ownership of their goals and development.
- Provide resources and support to help staff achieve their goals.
""", 9)

    add(
        "guide_10_unachieved_goals", "Next Year Goals", "Handling Unachieved Goals From Last Year", """
Section 7 (continued): If Last Year's Goals Were Not Achieved

If last year's goals were not achieved, the Line Manager will:
- Include those goals in the next year's plan with revised targets, deadlines, and weightage if applicable.
- Discuss and document the reasons for non-achievement.
""", 10)

    add(
        "guide_11_submission", "Submission", "Submission & Acknowledgement", """
Section 8: Submission & Acknowledgement

Following the appraisal and goals discussion:
- All evaluations are submitted digitally through the FlowHCM Appraisal System. No Excel sheets or
  physical appraisal forms are required.
- Each department will submit a hard copy of the Annual Appraisal Acknowledgement Sheet — with the
  signature of each individual — to the HR Department.
""", 11)

    add(
        "guide_12_eligibility", "Eligibility", "Eligibility Criteria", """
Section 9: Eligibility Criteria

Employees will be eligible for the appraisal cycle if they:
- Are permanent employees; and
- Have completed a minimum of three (3) months of service as of 30 June 2026
  (i.e., joined on or before 1 April 2026).
""", 12)

    add(
        "guide_13_timeline", "Timeline", "Appraisal Timeline", """
Section 10: Appraisal Timeline

- Self-Evaluation Phase: 15th June 2026 – 30th June 2026
- Line Manager Evaluation Phase: 1st July 2026 – 25th July 2026
- Management Evaluation Phase: 25th July – 31 August 2026
""", 13)

    print(f"  Guideline chunks       : {len(chunks)}")
    return chunks


# ══════════════════════════════════════════════════════════════════════════
# ABOUT BACHAA PARTY — general company info, no images
# doc_source = 'company_info'
# Source: About_Bachaa_Party.docx
# ══════════════════════════════════════════════════════════════════════════

def build_company_info_chunks(docx_path: str | None = None) -> list[PMSChunk]:
    """
    Build chunks for the 'About Bachaa Party' company overview doc.
    doc_source = 'company_info'

    docx_path is accepted for interface consistency / hash-tracking, but
    content is authored directly (short doc, no images or tables).
    """
    chunks: list[PMSChunk] = []

    def add(chunk_id: str, title: str, content: str, order: int):
        chunks.append(PMSChunk(
            chunk_id=chunk_id, content=content.strip(),
            section="Company Info", step_number=order, step_title=title,
            has_image=False, image_filename="", image_data="",
            chunk_type="company_info", doc_source="company_info",
        ))

    add(
        "company_01_overview", "About Bachaa Party — Overview", """
About Bachaa Party

Bachaa Party is Pakistan's first and biggest kids' retail store, founded by Ahmer Javed and
Omair Javed in Karachi in 2016. The brand is a one-stop destination for everything children need,
catering to kids aged 0–14 years.
""", 1)

    add(
        "company_02_products_footprint", "Product Range & Store Footprint", """
Bachaa Party — Product Range & Store Footprint

Product Range:
- Kids apparel (boys & girls)
- Kids shoes
- Toys and educational/creative toys
- Accessories
- Infant essentials and baby care
- Books and stationery
- Party supplies and crockery
- School supplies
- Sports accessories

Store Footprint:
Bachaa Party has grown from a single Karachi flagship store into a nationwide retail network with
13+ interactive outlets across Pakistan, including locations in Karachi, Lahore, Islamabad,
Rawalpindi, Hyderabad, Multan, and Gujranwala. The brand also operates a national e-commerce
platform at bachaaparty.com.
""", 2)

    print(f"  Company info chunks    : {len(chunks)}")
    return chunks