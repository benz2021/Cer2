import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from io import BytesIO
import zipfile
import re

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
def fix_thai_text(text):
    """
    จัดตำแหน่งสระและวรรณยุกต์ภาษาไทยให้ถูกต้อง (แก้ปัญหาสระจม/ลอย)
    โดยแทนที่ด้วยอักขระพิเศษ (PUA) ที่ฟอนต์ภาษาไทยส่วนใหญ่รองรับ
    """
    if not isinstance(text, str):
        return str(text) if pd.notna(text) else ""
        
    # กลุ่มวรรณยุกต์ปกติ ่ ้ ๊ ๋ ์
    tone_marks = ['\u0e48', '\u0e49', '\u0e4a', '\u0e4b', '\u0e4c']
    
    # 1. วรรณยุกต์ที่ตามหลังสระบน (ต้องดันวรรณยุกต์ขึ้นไปอีกระดับ)
    upper_vowels = ['\u0e31', '\u0e34', '\u0e35', '\u0e36', '\u0e37', '\u0e4d']
    high_tone_marks = ['\uf713', '\uf714', '\uf715', '\uf716', '\uf717']
    
    for i, tone in enumerate(tone_marks):
        for vowel in upper_vowels:
            text = text.replace(vowel + tone, vowel + high_tone_marks[i])
    
    # 2. วรรณยุกต์ที่ตามหลัง ป ฝ ฟ (ต้องเลี้ยวซ้ายหลบหางพยัญชนะ)
    tall_consonants = ['ป', 'ฝ', 'ฟ']
    left_tone_marks = ['\uf70a', '\uf70b', '\uf70c', '\uf70d', '\uf70e']
    
    for i, tone in enumerate(tone_marks):
        for cons in tall_consonants:
            text = text.replace(cons + tone, cons + left_tone_marks[i])
            
    # 3. จัดการสระอำ (นิคหิต + สระอา)
    text = text.replace('\u0e4d\u0e32', '\u0e33')
    
    return text

def get_font_by_name(font_name, size):
    """โหลดฟอนต์ตามชื่อที่กำหนด"""
    if font_name and font_name in st.session_state.fonts:
        try:
            return ImageFont.truetype(BytesIO(st.session_state.fonts[font_name]['data']), size)
        except Exception as e:
            st.error(f"ฟอนต์ '{font_name}' มีปัญหา: {e}")
            return ImageFont.load_default()
    # ใช้ฟอนต์เริ่มต้น (default font) ถ้าไม่พบ
    return ImageFont.load_default()

def get_font(size):
    """โหลดฟอนต์จากไฟล์ที่ผู้ใช้อัปโหลด (สำหรับ backward compatibility)"""
    return get_font_by_name(st.session_state.get('current_font', 'Default'), size)

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
        
        # ใช้ฟอนต์ที่กำหนดในแต่ละข้อความ
        font_name = txt.get('font_name', 'Default')
        font = get_font_by_name(font_name, txt['size'])
        
        text_width = draw.textlength(content, font=font)
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
if 'fonts' not in st.session_state: st.session_state.fonts = {}
if 'current_font' not in st.session_state: st.session_state.current_font = 'Default'

st.title(" Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1️⃣ อัปโหลดไฟล์")
    
    # 1. Template
    template_file = st.file_uploader("1. พื้นหลังเกียรติบัตร (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)

    # 2. Font Management
    st.subheader("📚 จัดการฟอนต์")
    
    # เพิ่มฟอนต์ใหม่
    new_font_file = st.file_uploader("เพิ่มฟอนต์ภาษาไทย (.ttf)", type=['ttf'], key="new_font_uploader")
    new_font_name = st.text_input("ชื่อฟอนต์ (สำหรับเลือก)", placeholder="เช่น: THSarabun, THSarabunNew")
    
    if new_font_file and new_font_name:
        if st.button("➕ เพิ่มฟอนต์"):
            font_data = new_font_file.getvalue()
            st.session_state.fonts[new_font_name] = {
                'name': new_font_name,
                'data': font_data,
                'file_name': new_font_file.name
            }
            st.success(f"✅ เพิ่มฟอนต์ '{new_font_name}' สำเร็จ!")
            st.rerun()
    
    # แสดงรายการฟอนต์ที่มี
    if st.session_state.fonts:
        st.markdown("**ฟอนต์ที่มีอยู่:**")
        for font_name in st.session_state.fonts.keys():
            col1, col2 = st.columns([3, 1])
            col1.write(f"- {font_name}")
            if col2.button("🗑️", key=f"del_font_{font_name}"):
                del st.session_state.fonts[font_name]
                if st.session_state.current_font == font_name:
                    st.session_state.current_font = 'Default'
                st.rerun()
    
    st.info("💡 เลือกฟอนต์ 'Default' เพื่อใช้ฟอนต์เริ่มต้นของระบบ")
    
    # 3. Data
    data_file = st.file_uploader("3. รายชื่อ (ไฟล์ Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    if data_file:
        if data_file.name.endswith('.csv'):
            st.session_state.data = pd.read_csv(data_file)
        else:
            st.session_state.data = pd.read_excel(data_file)

if 'template' not in st.session_state:
    st.info("👈 กรุณาอัปโหลด 'ต้นแบบเกียรติบัตร' ที่เมนูด้านซ้ายเพื่อเริ่มต้น")
    st.stop()

# --- MAIN AREA ---
st.header("2️⃣ กำหนดตำแหน่ง ")

col_img, col_form = st.columns([1.5, 1])

with col_img:
    st.markdown("**🖱️ คลิกลงบนรูปภาพเพื่อดึงพิกัด (คลิกบนรูป หรือ ระบุ X และ Y)**")
    
    # คำนวณการย่อภาพ
    original_w, original_h = st.session_state.template.size
    display_w = 700 
    
    if original_w > display_w:
        ratio = original_w / display_w
        display_img = st.session_state.template.resize((display_w, int(original_h / ratio)))
    else:
        ratio = 1.0
        display_img = st.session_state.template

    coords = streamlit_image_coordinates(display_img, key="target_clicker")
    
    if coords is not None:
        st.session_state.click_x = int(coords['x'] * ratio)
        st.session_state.click_y = int(coords['y'] * ratio)

with col_form:
    st.markdown("**📝 ตั้งค่าข้อความ**")
    with st.form("add_text_form", clear_on_submit=False):
        t_type = st.radio("ชนิดข้อมูล", ["พิมพ์เอง", "ดึงจาก Excel"], horizontal=True)
        
        t_val, t_col = "", ""
        if "พิมพ์เอง" in t_type:
            t_val = st.text_input("ระบุข้อความ")
        else:
            if 'data' in st.session_state:
                t_col = st.selectbox("เลือกหัวข้อ (Column)", st.session_state.data.columns)
            else:
                st.warning("อัปโหลด Excel ก่อนครับ")

        c1, c2 = st.columns(2)
        x_pos = c1.number_input("แกน X", value=st.session_state.click_x)
        y_pos = c2.number_input("แกน Y", value=st.session_state.click_y)
        
        f_size = st.slider("ขนาดฟอนต์", 10, 500, value=60)
        f_color = st.color_picker("เลือกสี", value="#000000")
        
        # เลือกฟอนต์สำหรับข้อความนี้
        font_options = ['Default'] + list(st.session_state.fonts.keys())
        selected_font = st.selectbox("เลือกฟอนต์", font_options, index=0)
        
        if st.form_submit_button("➕ แทรกข้อความลงเกียรติบัตร"):
            st.session_state.texts.append({
                'type': 'static' if "พิมพ์เอง" in t_type else 'excel',
                'text': t_val, 
                'column': t_col,
                'x': x_pos, 
                'y': y_pos,
                'size': f_size, 
                'color': f_color,
                'font_name': selected_font  # เก็บชื่อฟอนต์ที่เลือก
            })
            st.rerun()

st.markdown("---")

# --- พรีวิวและจัดการข้อความ ---
st.header("3️⃣ ดูตัวอย่าง (Preview)")

if st.session_state.texts:
    for i, t in enumerate(st.session_state.texts):
        lbl = t['text'] if t['type'] == 'static' else f"จาก: {t['column']}"
        font_display = t.get('font_name', 'Default')
        cols = st.columns([4, 1])
        cols[0].write(f"**{i+1}. {lbl}** | ขนาด: {t['size']} | ฟอนต์: {font_display} | พิกัด: ({t['x']}, {t['y']})")
        if cols[1].button("🗑️ ลบ", key=f"del_{i}"):
            st.session_state.texts.pop(i)
            st.rerun()

    preview_row = None
    if 'data' in st.session_state:
        row_idx = st.number_input("ดูตัวอย่างแถวที่:", 0, max(0, len(st.session_state.data)-1), 0)
        preview_row = st.session_state.data.iloc[row_idx].to_dict()
    
    preview_img = render_certificate(st.session_state.template, st.session_state.texts, preview_row)
    st.image(preview_img, width=650)
else:
    st.info("ตั้งค่าข้อความด้านบนก่อนครับ")

# --- Export ---
if 'data' in st.session_state and st.session_state.texts:
    st.markdown("---")
    st.header("4️⃣ สร้างไฟล์ทั้งหมด")
    filename_col = st.selectbox("เลือกคอลัมน์ชื่อไฟล์", st.session_state.data.columns)
    
    if st.button("สร้างไฟล์", type="primary"):
        zip_buffer = BytesIO()
        with st.spinner("กำลังสร้างเกียรติบัตร..."):
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                for idx, row in st.session_state.data.iterrows():
                    final_img = render_certificate(st.session_state.template, st.session_state.texts, row.to_dict())
                    img_io = BytesIO()
                    final_img.save(img_io, format="PNG")
                    clean_name = sanitize_filename(row[filename_col])
                    zf.writestr(f"{clean_name}.png", img_io.getvalue())
            
            st.success("สำเร็จ!")
            st.download_button("📥 ดาวน์โหลดไฟล์ ZIP", zip_buffer.getvalue(), "certificates.zip", "application/zip")