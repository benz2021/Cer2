import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from io import BytesIO
import zipfile
import re
import os

# --- นำเข้าไลบรารีสำหรับคลิกหาพิกัด ---
try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:
    st.error("⚠️ ไม่พบไลบรารี streamlit-image-coordinates")
    st.info("กรุณาเปิด Terminal แล้วพิมพ์: pip install streamlit-image-coordinates")
    st.stop()

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================

def get_system_font_path():
    """ค้นหาฟอนต์ที่ปรับขนาดได้ในระบบเพื่อใช้เป็นสำรอง"""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "/System/Library/Fonts/Helvetica.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def fix_thai_text(text):
    """จัดตำแหน่งสระและวรรณยุกต์ภาษาไทยให้ถูกต้อง"""
    if not isinstance(text, str):
        return str(text) if pd.notna(text) else ""
    tone_marks = ['\u0e48', '\u0e49', '\u0e4a', '\u0e4b', '\u0e4c']
    upper_vowels = ['\u0e31', '\u0e34', '\u0e35', '\u0e36', '\u0e37', '\u0e4d']
    high_tone_marks = ['\uf713', '\uf714', '\uf715', '\uf716', '\uf717']
    for i, tone in enumerate(tone_marks):
        for vowel in upper_vowels:
            text = text.replace(vowel + tone, vowel + high_tone_marks[i])
    tall_consonants = ['ป', 'ฝ', 'ฟ']
    left_tone_marks = ['\uf70a', '\uf70b', '\uf70c', '\uf70d', '\uf70e']
    for i, tone in enumerate(tone_marks):
        for cons in tall_consonants:
            text = text.replace(cons + tone, cons + left_tone_marks[i])
    text = text.replace('\u0e4d\u0e32', '\u0e33')
    return text

def get_font(font_name, size):
    """ดึงฟอนต์ตามชื่อและขนาดจากหน่วยความจำ"""
    if font_name in st.session_state.fonts_dict:
        font_data = st.session_state.fonts_dict[font_name]
        try:
            return ImageFont.truetype(BytesIO(font_data), size)
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดฟอนต์ '{font_name}': {e}")
    
    # หากไม่พบฟอนต์ที่ระบุ พยายามใช้ฟอนต์ระบบที่ปรับขนาดได้
    sys_path = get_system_font_path()
    if sys_path:
        return ImageFont.truetype(sys_path, size)
    return ImageFont.load_default()

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', str(name)).strip() or "certificate"

def render_certificate(template_img, texts, row_data=None):
    img = template_img.copy()
    if img.mode != 'RGB':
        img = img.convert('RGB')
    draw = ImageDraw.Draw(img)
    
    for txt in texts:
        if txt['type'] == 'static':
            content = txt['text']
        else:
            if row_data and txt['column'] in row_data:
                val = row_data[txt['column']]
                content = str(val) if pd.notna(val) else ""
            else:
                content = "ตัวอย่างข้อมูล"
        
        if not content: continue
        
        # แก้สระภาษาไทย
        content = fix_thai_text(content)
            
        # ใช้ฟอนต์ที่บันทึกไว้สำหรับข้อความนี้โดยเฉพาะ
        font = get_font(txt.get('font_name'), txt['size'])

        # วัดขนาดและจัดกึ่งกลาง
        try:
            text_bbox = font.getbbox(content)
            text_width = text_bbox[2] - text_bbox[0]
        except:
            text_width = draw.textlength(content, font=font)

        # คำนวณจุดเริ่มต้น x (ถอยกลับไปครึ่งหนึ่งของความกว้างข้อความ เพื่อให้จุด x เป็นจุดกึ่งกลางพอดี)
        start_x = txt['x'] - (text_width / 2)
        draw.text((start_x, txt['y']), content, fill=txt['color'], font=font, anchor="ls")
    return img

# ==========================================
# 🎨 UI - STREAMLIT APP
# ==========================================
st.set_page_config(page_title="Auto Cert Pro", layout="wide")

# ตั้งค่า Session State
if "click_x" not in st.session_state: st.session_state.click_x = 0
if "click_y" not in st.session_state: st.session_state.click_y = 0
if 'texts' not in st.session_state: st.session_state.texts = []
if 'fonts_dict' not in st.session_state: st.session_state.fonts_dict = {}
if 'font_names' not in st.session_state: st.session_state.font_names = []

st.title("📜 Auto Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1️⃣ อัปโหลดไฟล์")
    
    # 1. Template
    template_file = st.file_uploader("🖼️ พื้นหลังเกียรติบัตร (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)

    # 2. Font Management
    st.markdown("---")
    st.header("2️⃣ จัดการฟอนต์")
    uploaded_font = st.file_uploader("🔤 อัปโหลดฟอนต์ใหม่ (.ttf)", type=['ttf'])
    if uploaded_font:
        # ใช้ชื่อไฟล์เป็นชื่อฟอนต์อัตโนมัติ
        f_name = uploaded_font.name.split('.')[0]
        if f_name not in st.session_state.fonts_dict:
            st.session_state.fonts_dict[f_name] = uploaded_font.getvalue()
            st.session_state.font_names.append(f_name)
            st.success(f"✅ เพิ่มฟอนต์ '{f_name}' แล้ว")

    # 3. Data
    st.markdown("---")
    st.header("3️⃣ รายชื่อข้อมูล")
    data_file = st.file_uploader("📊 ไฟล์ Excel/CSV", type=['xlsx', 'xls', 'csv'])
    if data_file:
        if data_file.name.endswith('.csv'):
            st.session_state.data = pd.read_csv(data_file)
        else:
            st.session_state.data = pd.read_excel(data_file)

if 'template' not in st.session_state:
    st.info("👈 กรุณาอัปโหลด 'พื้นหลังเกียรติบัตร' ที่เมนูด้านซ้ายเพื่อเริ่มต้น")
    st.stop()

# --- MAIN AREA ---
st.header("📍 กำหนดตำแหน่งและข้อความ")

col_img, col_form = st.columns([1.5, 1])

with col_img:
    st.markdown("**🖱️ คลิกลงบนรูปภาพเพื่อระบุตำแหน่ง X และ Y**")
    original_w, original_h = st.session_state.template.size
    display_w = 700 
    ratio = original_w / display_w if original_w > display_w else 1.0
    display_img = st.session_state.template.resize((display_w, int(original_h / ratio))) if original_w > display_w else st.session_state.template

    coords = streamlit_image_coordinates(display_img, key="target_clicker")
    if coords:
        st.session_state.click_x = int(coords['x'] * ratio)
        st.session_state.click_y = int(coords['y'] * ratio)

with col_form:
    with st.form("add_text_form", clear_on_submit=True):
        t_type = st.radio("ชนิดข้อความ", ["พิมพ์เอง", "ดึงจากไฟล์รายชื่อ"], horizontal=True)
        t_val = st.text_input("ข้อความ (ถ้าพิมพ์เอง)")
        t_col = st.selectbox("เลือกหัวข้อ (ถ้าดึงจากไฟล์)", st.session_state.data.columns if 'data' in st.session_state else ["กรุณาอัปโหลดไฟล์รายชื่อ"])
        
        c1, c2 = st.columns(2)
        x_pos = c1.number_input("ตำแหน่ง X", value=st.session_state.click_x)
        y_pos = c2.number_input("ตำแหน่ง Y", value=st.session_state.click_y)
        
        f_size = st.slider("ขนาดฟอนต์", 10, 500, value=60)
        f_color = st.color_picker("เลือกสีข้อความ", value="#000000")
        
        # เลือกฟอนต์ (บังคับเลือกจากที่อัปโหลด)
        if not st.session_state.font_names:
            st.warning("⚠️ กรุณาอัปโหลดฟอนต์ที่เมนูด้านซ้ายก่อน")
            selected_font = None
        else:
            selected_font = st.selectbox("เลือกฟอนต์สำหรับข้อความนี้", st.session_state.font_names)
        
        if st.form_submit_button("➕ เพิ่มข้อความลงเกียรติบัตร"):
            if selected_font:
                st.session_state.texts.append({
                    'type': 'static' if "พิมพ์เอง" in t_type else 'excel',
                    'text': t_val, 'column': t_col,
                    'x': x_pos, 'y': y_pos,
                    'size': f_size, 'color': f_color,
                    'font_name': selected_font
                })
                st.success("เพิ่มข้อความสำเร็จ!")
                st.rerun()
            else:
                st.error("กรุณาอัปโหลดและเลือกฟอนต์ก่อนเพิ่มข้อความ")

st.markdown("---")
st.header("👁️ ตรวจสอบและพรีวิว")

if st.session_state.texts:
    for i, t in enumerate(st.session_state.texts):
        lbl = t['text'] if t['type'] == 'static' else f"คอลัมน์: {t['column']}"
        cols = st.columns([4, 1])
        cols[0].write(f"**{i+1}. {lbl}** | ฟอนต์: {t['font_name']} | ขนาด: {t['size']} | พิกัด: ({t['x']}, {t['y']})")
        if cols[1].button("🗑️ ลบ", key=f"del_{i}"):
            st.session_state.texts.pop(i)
            st.rerun()

    preview_row = st.session_state.data.iloc[st.number_input("ดูตัวอย่างจากรายชื่อแถวที่:", 0, max(0, len(st.session_state.data)-1), 0)].to_dict() if 'data' in st.session_state else None
    st.image(render_certificate(st.session_state.template, st.session_state.texts, preview_row), width=700)
else:
    st.info("ยังไม่มีข้อความถูกเพิ่ม")

# --- Export ---
if 'data' in st.session_state and st.session_state.texts:
    st.markdown("---")
    st.header("📦 สร้างและดาวน์โหลด")
    
    c1, c2 = st.columns(2)
    filename_col = c1.selectbox("เลือกคอลัมน์ที่จะใช้เป็นชื่อไฟล์", st.session_state.data.columns)
    # เพิ่ม UI สำหรับเลือกประเภทไฟล์ที่ต้องการ Export
    file_format = c2.radio("เลือกรูปแบบไฟล์ส่งออก", ["PNG", "PDF"], horizontal=True)
    
    if st.button("🚀 เริ่มสร้างเกียรติบัตรทั้งหมด", type="primary"):
        zip_buffer = BytesIO()
        with st.spinner("กำลังประมวลผล..."):
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                for _, row in st.session_state.data.iterrows():
                    final_img = render_certificate(st.session_state.template, st.session_state.texts, row.to_dict())
                    img_io = BytesIO()
                    
                    # ตรวจสอบรูปแบบไฟล์ที่ผู้ใช้เลือก
                    if file_format == "PNG":
                        final_img.save(img_io, format="PNG")
                        ext = "png"
                    else:  # PDF
                        # Pillow บังคับว่าภาพที่จะเซฟเป็น PDF ต้องอยู่ในโหมด RGB (ซึ่งฟังก์ชัน render ทำไว้ให้แล้ว)
                        final_img.save(img_io, format="PDF")
                        ext = "pdf"
                        
                    zf.writestr(f"{sanitize_filename(row[filename_col])}.{ext}", img_io.getvalue())
                    
        st.success("สร้างไฟล์ทั้งหมดเรียบร้อย!")
        st.download_button(f"📥 ดาวน์โหลดไฟล์ทั้งหมด ({file_format} ใน ZIP)", zip_buffer.getvalue(), "certificates.zip", "application/zip")
