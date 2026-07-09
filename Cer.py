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

def get_font(font_name, size):
    """ดึงฟอนต์ตามชื่อและขนาด"""
    # ถ้าเป็น Default หรือไม่มีฟอนต์ในระบบ
    if font_name == 'Default' or not font_name:
        # ลองใช้ฟอนต์เริ่มต้นของ PIL (อาจไม่รองรับภาษาไทย)
        try:
            return ImageFont.load_default()
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดฟอนต์เริ่มต้นของ PIL ได้: {e}")
            return None
    
    # โหลดจากฟอนต์ที่ผู้ใช้เพิ่ม
    if font_name in st.session_state.fonts_dict:
        font_data = st.session_state.fonts_dict[font_name]
        try:
            return ImageFont.truetype(BytesIO(font_data), size)
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดฟอนต์ '{font_name}': {e}")
            return ImageFont.load_default()
    
    # หากไม่พบฟอนต์ที่ระบุ ให้ใช้ฟอนต์เริ่มต้นของ PIL
    st.warning(f"⚠️ ไม่พบฟอนต์ '{font_name}' กำลังใช้ฟอนต์เริ่มต้นของ PIL (อาจไม่รองรับภาษาไทย)")
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
        
        # === เรียกใช้ฟังก์ชันแก้สระภาษาไทยตรงนี้ ===
        # content = fix_thai_text(content)
            
        font = get_font(txt.get('font_name', 'Default'), txt['size'])

        # 1. ให้โปรแกรมวัดความกว้างของข้อความนั้นๆ ก่อน (หน่วยเป็นพิกเซล)
        text_width = draw.textlength(content, font=font)

        # 2. คำนวณหาจุด X ทางซ้ายสุด (เอาพิกัดแกน X ที่คลิกไว้ ลบด้วย ครึ่งหนึ่งของความกว้างข้อความ)
        start_x = txt['x'] - (text_width / 2)

        # 3. สั่งวาดข้อความ โดยเริ่มจากจุด start_x ที่คำนวณได้ และใช้ anchor="ls" (หรือ "la") เหมือนเดิม
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
if 'fonts_dict' not in st.session_state: st.session_state.fonts_dict = {} # เก็บข้อมูลฟอนต์ที่อัปโหลดแยกตามชื่อ
if 'font_names' not in st.session_state: st.session_state.font_names = [] # เก็บรายชื่อฟอนต์สำหรับแสดงใน dropdown

st.title(" Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1️⃣ อัปโหลดไฟล์")
    
    # 1. Template
    template_file = st.file_uploader("1. พื้นหลังเกียรติบัตร (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)

    # 2. Font (ย้ายไปจัดการในส่วนเพิ่มข้อความเพื่อให้ยืดหยุ่นขึ้น)
    # เก็บไว้เผื่อผู้ใช้ต้องการอัปโหลดฟอนต์เริ่มต้น
    st.markdown("**2. จัดการฟอนต์**")
    with st.expander("➕ เพิ่มฟอนต์ใหม่"):
        new_font_file = st.file_uploader("อัปโหลดไฟล์ฟอนต์ (.ttf)", type=['ttf'], key="sidebar_font")
        new_font_name = st.text_input("ตั้งชื่อฟอนต์", placeholder="เช่น: THSarabun")
        if st.button("บันทึกฟอนต์", key="save_sidebar_font"):
            if new_font_file and new_font_name:
                st.session_state.fonts_dict[new_font_name] = new_font_file.getvalue()
                if new_font_name not in st.session_state.font_names:
                    st.session_state.font_names.append(new_font_name)
                st.success(f"✅ บันทึกฟอนต์ '{new_font_name}' สำเร็จ")
                st.rerun()
            else:
                st.warning("กรุณาอัปโหลดไฟล์และตั้งชื่อฟอนต์")

    # 3. Data
    data_file = st.file_uploader("3. รายชื่อ (ไฟล์ Excel/CSV)  ", type=['xlsx', 'xls', 'csv'])
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
    st.markdown("**🖱️ คลิกลงบนรูปภาพเพื่อดึงพิกัด(คลิกบนรูป หรือ ระบุ X และ Y)**")
    
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
        
        # ส่วนเลือกฟอนต์สำหรับข้อความนี้
        font_options = ["Default"] + st.session_state.font_names
        selected_font = st.selectbox("เลือกฟอนต์สำหรับข้อความนี้", font_options)
        
        if st.form_submit_button("➕ แทรกข้อความลงเกียรติบัตร"):
            st.session_state.texts.append({
                'type': 'static' if "พิมพ์เอง" in t_type else 'excel',
                'text': t_val, 'column': t_col,
                'x': x_pos, 'y': y_pos,
                'size': f_size, 'color': f_color,
                'font_name': selected_font # บันทึกชื่อฟอนต์เฉพาะสำหรับข้อความนี้
            })
            st.rerun()

st.markdown("---")

# --- พรีวิวและจัดการข้อความ ---
st.header("3️⃣ ดูตัวอย่าง (Preview)")

if st.session_state.texts:
    for i, t in enumerate(st.session_state.texts):
        lbl = t['text'] if t['type'] == 'static' else f"จาก: {t['column']}"
        cols = st.columns([4, 1])
        cols[0].write(f"**{i+1}. {lbl}** | ขนาด: {t['size']} | พิกัด: ({t['x']}, {t['y']}) | ฟอนต์: {t.get('font_name', 'Default')}")
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
                    # ต้องสร้างสำเนาของ texts เพื่อไม่ให้กระทบกับ session_state เดิม
                    texts_to_render_for_this_cert = st.session_state.texts.copy()
                    
                    final_img = render_certificate(st.session_state.template, texts_to_render_for_this_cert, row.to_dict())
                    img_io = BytesIO()
                    final_img.save(img_io, format="PNG")
                    clean_name = sanitize_filename(row[filename_col])
                    zf.writestr(f"{clean_name}.png", img_io.getvalue())
            
            st.success("สำเร็จ!")
            st.download_button("📥 ดาวน์โหลดไฟล์ ZIP", zip_buffer.getvalue(), "certificates.zip", "application/zip")
