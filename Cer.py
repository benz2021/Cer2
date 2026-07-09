import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from io import BytesIO
import zipfile
import re
import tempfile
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

# Cache fonts เพื่อเพิ่มประสิทธิภาพ
@st.cache_resource
def load_font_from_bytes(font_data, font_size):
    """โหลดฟอนต์จาก bytes และแคชไว้"""
    try:
        # สร้างไฟล์ชั่วคราวสำหรับฟอนต์
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ttf') as tmp_file:
            tmp_file.write(font_data)
            tmp_path = tmp_file.name
        
        # โหลดฟอนต์จากไฟล์ชั่วคราว
        font = ImageFont.truetype(tmp_path, font_size)
        
        # ลบไฟล์ชั่วคราวหลังจากโหลดแล้ว (PIL จะเก็บข้อมูลในหน่วยความจำ)
        try:
            os.unlink(tmp_path)
        except:
            pass
            
        return font
    except Exception as e:
        st.warning(f"ไม่สามารถโหลดฟอนต์ได้: {e}")
        # ใช้ฟอนต์เริ่มต้นของ PIL
        return ImageFont.load_default()

@st.cache_resource
def get_default_font(size):
    """สร้างฟอนต์เริ่มต้นที่มีขนาด"""
    try:
        # ลองใช้ฟอนต์ระบบทั่วไป
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
            'C:\\Windows\\Fonts\\Arial.ttf',  # Windows
            '/System/Library/Fonts/Helvetica.ttf',  # macOS
        ]
        for path in font_paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    except:
        pass
    
    # ถ้าไม่พบ ให้ใช้ฟอนต์เริ่มต้น
    return ImageFont.load_default()

def get_font_by_name(font_name, size):
    """โหลดฟอนต์ตามชื่อที่กำหนด พร้อมปรับขนาด"""
    # ถ้าเป็น Default หรือไม่มีฟอนต์
    if font_name == 'Default' or not font_name or font_name not in st.session_state.fonts:
        return get_default_font(size)
    
    # โหลดฟอนต์จาก cache
    font_data = st.session_state.fonts[font_name]['data']
    try:
        return load_font_from_bytes(font_data, size)
    except Exception as e:
        st.warning(f"ไม่สามารถโหลดฟอนต์ '{font_name}' ได้: {e}")
        return get_default_font(size)

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
        
        # วัดความกว้างข้อความ
        try:
            text_width = draw.textlength(content, font=font)
        except:
            # ถ้าไม่สามารถวัดได้ ให้ใช้วิธีอื่น
            bbox = draw.textbbox((0, 0), content, font=font)
            text_width = bbox[2] - bbox[0]
        
        start_x = txt['x'] - (text_width / 2)
        
        # วาดข้อความ
        try:
            draw.text((start_x, txt['y']), content, fill=txt['color'], font=font, anchor="ls")
        except Exception as e:
            st.warning(f"ไม่สามารถวาดข้อความได้: {e}")
            # ลองใช้วิธีแบบไม่ระบุ anchor
            draw.text((start_x, txt['y']), content, fill=txt['color'], font=font)
    
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

st.title("🎓 Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1️⃣ อัปโหลดไฟล์")
    
    # 1. Template
    template_file = st.file_uploader("1. พื้นหลังเกียรติบัตร (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)
        st.success("✅ โหลดเทมเพลตสำเร็จ")

    # 2. Font Management
    st.subheader("📚 จัดการฟอนต์")
    
    st.info("💡 อัปโหลดฟอนต์ .ttf เพื่อให้สามารถปรับขนาดและแสดงภาษาไทยได้")
    
    # เพิ่มฟอนต์ใหม่
    new_font_file = st.file_uploader("เพิ่มฟอนต์ภาษาไทย (.ttf)", type=['ttf'], key="new_font_uploader")
    new_font_name = st.text_input("ชื่อฟอนต์ (สำหรับเลือก)", placeholder="เช่น: THSarabun, THSarabunNew")
    
    col1, col2 = st.columns(2)
    with col1:
        if new_font_file and new_font_name:
            if st.button("➕ เพิ่มฟอนต์", use_container_width=True):
                font_data = new_font_file.getvalue()
                # ทดสอบโหลดฟอนต์
                try:
                    test_font = load_font_from_bytes(font_data, 20)
                    st.session_state.fonts[new_font_name] = {
                        'name': new_font_name,
                        'data': font_data,
                        'file_name': new_font_file.name
                    }
                    st.success(f"✅ เพิ่มฟอนต์ '{new_font_name}' สำเร็จ!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ ฟอนต์ไม่ถูกต้อง: {e}")
    
    # แสดงรายการฟอนต์ที่มี
    if st.session_state.fonts:
        st.markdown("**ฟอนต์ที่มีอยู่:**")
        for font_name in st.session_state.fonts.keys():
            col1, col2 = st.columns([3, 1])
            col1.write(f"📝 {font_name}")
            if col2.button("🗑️", key=f"del_font_{font_name}"):
                del st.session_state.fonts[font_name]
                if st.session_state.current_font == font_name:
                    st.session_state.current_font = 'Default'
                st.rerun()
    else:
        st.warning("⚠️ ยังไม่มีฟอนต์ที่อัปโหลด (ใช้ฟอนต์เริ่มต้นของระบบ)")
    
    # 3. Data
    data_file = st.file_uploader("3. รายชื่อ (ไฟล์ Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    if data_file:
        try:
            if data_file.name.endswith('.csv'):
                st.session_state.data = pd.read_csv(data_file)
            else:
                st.session_state.data = pd.read_excel(data_file)
            st.success(f"✅ โหลดข้อมูลสำเร็จ: {len(st.session_state.data)} รายการ")
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดข้อมูลได้: {e}")

if 'template' not in st.session_state:
    st.info("👈 กรุณาอัปโหลด 'ต้นแบบเกียรติบัตร' ที่เมนูด้านซ้ายเพื่อเริ่มต้น")
    st.stop()

# --- MAIN AREA ---
st.header("2️⃣ กำหนดตำแหน่งข้อความ")

col_img, col_form = st.columns([1.5, 1])

with col_img:
    st.markdown("**🖱️ คลิกลงบนรูปภาพเพื่อดึงพิกัด**")
    
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
        st.success(f"📍 พิกัดที่เลือก: X={st.session_state.click_x}, Y={st.session_state.click_y}")

with col_form:
    st.markdown("**📝 ตั้งค่าข้อความ**")
    with st.form("add_text_form", clear_on_submit=False):
        t_type = st.radio("ชนิดข้อมูล", ["พิมพ์เอง", "ดึงจาก Excel"], horizontal=True)
        
        t_val, t_col = "", ""
        if "พิมพ์เอง" in t_type:
            t_val = st.text_input("ระบุข้อความ", placeholder="พิมพ์ข้อความที่ต้องการ")
        else:
            if 'data' in st.session_state:
                t_col = st.selectbox("เลือกหัวข้อ (Column)", st.session_state.data.columns)
            else:
                st.warning("⚠️ กรุณาอัปโหลดไฟล์ Excel/CSV ก่อน")
                t_col = ""

        c1, c2 = st.columns(2)
        x_pos = c1.number_input("แกน X", value=st.session_state.click_x)
        y_pos = c2.number_input("แกน Y", value=st.session_state.click_y)
        
        f_size = st.slider("ขนาดฟอนต์", 10, 500, value=60, step=5)
        f_color = st.color_picker("เลือกสี", value="#000000")
        
        # เลือกฟอนต์สำหรับข้อความนี้
        font_options = ['Default'] + list(st.session_state.fonts.keys())
        selected_font = st.selectbox("เลือกฟอนต์", font_options, index=0)
        
        # แสดงตัวอย่างข้อความในฟอร์ม
        if t_val or t_col:
            sample_text = t_val if t_type == "พิมพ์เอง" else f"[{t_col}]"
            st.caption(f"📝 ตัวอย่าง: {sample_text}")
        
        if st.form_submit_button("➕ แทรกข้อความ", type="primary"):
            if t_type == "พิมพ์เอง" and not t_val:
                st.warning("⚠️ กรุณาพิมพ์ข้อความ")
            elif t_type == "ดึงจาก Excel" and not t_col:
                st.warning("⚠️ กรุณาเลือกหัวข้อจาก Excel")
            else:
                st.session_state.texts.append({
                    'type': 'static' if "พิมพ์เอง" in t_type else 'excel',
                    'text': t_val, 
                    'column': t_col,
                    'x': x_pos, 
                    'y': y_pos,
                    'size': f_size, 
                    'color': f_color,
                    'font_name': selected_font
                })
                st.success("✅ เพิ่มข้อความสำเร็จ!")
                st.rerun()

st.markdown("---")

# --- พรีวิวและจัดการข้อความ ---
st.header("3️⃣ ดูตัวอย่าง (Preview)")

if st.session_state.texts:
    # แสดงรายการข้อความทั้งหมด
    st.subheader("📋 รายการข้อความ")
    for i, t in enumerate(st.session_state.texts):
        lbl = t['text'] if t['type'] == 'static' else f"จาก: {t['column']}"
        font_display = t.get('font_name', 'Default')
        
        col1, col2, col3 = st.columns([4, 1, 0.5])
        col1.write(f"**{i+1}. {lbl}** | ขนาด: {t['size']} | ฟอนต์: {font_display}")
        col2.write(f"พิกัด: ({t['x']}, {t['y']})")
        if col3.button("🗑️", key=f"del_{i}"):
            st.session_state.texts.pop(i)
            st.rerun()
    
    # Preview
    st.subheader("👁️ ตัวอย่าง")
    preview_row = None
    if 'data' in st.session_state and len(st.session_state.data) > 0:
        row_idx = st.number_input("ดูตัวอย่างแถวที่:", 0, max(0, len(st.session_state.data)-1), 0, step=1)
        preview_row = st.session_state.data.iloc[row_idx].to_dict()
        
        # แสดงข้อมูลแถวนั้น
        with st.expander("📊 ดูข้อมูลแถวนั้น"):
            st.json(preview_row)
    
    # สร้างตัวอย่าง
    try:
        preview_img = render_certificate(st.session_state.template, st.session_state.texts, preview_row)
        st.image(preview_img, width=650)
    except Exception as e:
        st.error(f"❌ ไม่สามารถแสดงตัวอย่างได้: {e}")
else:
    st.info("💡 ตั้งค่าข้อความด้านบนก่อนครับ")

# --- Export ---
if 'data' in st.session_state and st.session_state.texts:
    st.markdown("---")
    st.header("4️⃣ สร้างไฟล์ทั้งหมด")
    
    col1, col2 = st.columns(2)
    with col1:
        filename_col = st.selectbox("เลือกคอลัมน์ชื่อไฟล์", st.session_state.data.columns)
    with col2:
        st.write("")
        st.write("")
        use_thai_fix = st.checkbox("แก้ไขตำแหน่งสระ/วรรณยุกต์", value=True)
    
    if st.button("🚀 สร้างไฟล์ ZIP", type="primary", use_container_width=True):
        zip_buffer = BytesIO()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("กำลังสร้างเกียรติบัตร..."):
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                total_rows = len(st.session_state.data)
                for idx, row in st.session_state.data.iterrows():
                    status_text.text(f"กำลังสร้าง: {idx+1}/{total_rows}")
                    
                    # แปลงข้อความถ้าต้องการ
                    texts_to_render = st.session_state.texts.copy()
                    if use_thai_fix:
                        for txt in texts_to_render:
                            if txt['type'] == 'static':
                                txt['text'] = fix_thai_text(txt['text'])
                    
                    final_img = render_certificate(st.session_state.template, texts_to_render, row.to_dict())
                    img_io = BytesIO()
                    final_img.save(img_io, format="PNG", optimize=True)
                    clean_name = sanitize_filename(row[filename_col])
                    zf.writestr(f"{clean_name}.png", img_io.getvalue())
                    
                    progress_bar.progress((idx + 1) / total_rows)
            
            status_text.text("✅ สร้างเสร็จสิ้น!")
            st.success("🎉 สร้างไฟล์ทั้งหมดสำเร็จ!")
            st.download_button(
                "📥 ดาวน์โหลด ZIP", 
                zip_buffer.getvalue(), 
                "certificates.zip", 
                "application/zip",
                use_container_width=True
            )
