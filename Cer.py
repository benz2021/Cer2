import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from io import BytesIO
import zipfile
import re
import tempfile
import os
import base64

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

# จัดการฟอนต์แบบ global
_font_cache = {}

def get_system_font_path():
    """ค้นหาฟอนต์ที่ติดตั้งในระบบ"""
    font_paths = [
        # Windows
        'C:\\Windows\\Fonts\\Arial.ttf',
        'C:\\Windows\\Fonts\\Tahoma.ttf',
        'C:\\Windows\\Fonts\\msyh.ttc',  # Microsoft YaHei
        # Linux
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        # macOS
        '/System/Library/Fonts/Helvetica.ttf',
        '/System/Library/Fonts/Arial.ttf',
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None

def load_font(font_data, size):
    """โหลดฟอนต์จาก bytes data ด้วยขนาดที่กำหนด"""
    # สร้าง cache key
    cache_key = f"{hash(font_data)}_{size}"
    
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    
    try:
        # สร้างไฟล์ชั่วคราว
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ttf') as tmp_file:
            tmp_file.write(font_data)
            tmp_path = tmp_file.name
        
        # โหลดฟอนต์
        font = ImageFont.truetype(tmp_path, size)
        
        # เก็บใน cache
        _font_cache[cache_key] = font
        
        # ลบไฟล์ชั่วคราว (PIL จะเก็บข้อมูลในหน่วยความจำ)
        try:
            os.unlink(tmp_path)
        except:
            pass
            
        return font
    except Exception as e:
        st.warning(f"ไม่สามารถโหลดฟอนต์ได้: {e}")
        # ใช้ฟอนต์ระบบแทน
        system_font = get_system_font_path()
        if system_font:
            try:
                font = ImageFont.truetype(system_font, size)
                _font_cache[cache_key] = font
                return font
            except:
                pass
        # สุดท้ายใช้ฟอนต์เริ่มต้น (แต่จะปรับขนาดไม่ได้)
        return ImageFont.load_default()

def get_font_by_name(font_name, size):
    """โหลดฟอนต์ตามชื่อ"""
    # กรณีไม่มีฟอนต์หรือเป็น Default
    if not font_name or font_name == 'Default' or font_name not in st.session_state.fonts:
        # ลองใช้ฟอนต์ระบบ
        system_font = get_system_font_path()
        if system_font:
            try:
                cache_key = f"system_{size}"
                if cache_key not in _font_cache:
                    _font_cache[cache_key] = ImageFont.truetype(system_font, size)
                return _font_cache[cache_key]
            except:
                pass
        # ใช้ฟอนต์เริ่มต้น (ปรับขนาดไม่ได้)
        return ImageFont.load_default()
    
    # โหลดจากฟอนต์ที่อัปโหลด
    font_data = st.session_state.fonts[font_name]['data']
    return load_font(font_data, size)

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
        
        if not content: 
            continue
        
        font_name = txt.get('font_name', 'Default')
        font = get_font_by_name(font_name, txt['size'])
        
        try:
            # วัดความกว้างข้อความ
            text_width = draw.textlength(content, font=font)
            start_x = txt['x'] - (text_width / 2)
            draw.text((start_x, txt['y']), content, fill=txt['color'], font=font, anchor="ls")
        except Exception as e:
            # ถ้าใช้ฟอนต์ default ที่ปรับขนาดไม่ได้
            st.warning(f"ไม่สามารถปรับขนาดฟอนต์ได้: {e}")
            # วาดโดยไม่ปรับขนาด
            draw.text((txt['x'], txt['y']), content, fill=txt['color'])
    
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
if 'font_list' not in st.session_state: st.session_state.font_list = []

st.title("🎓 Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1️⃣ อัปโหลดไฟล์")
    
    # 1. Template
    template_file = st.file_uploader("📄 พื้นหลังเกียรติบัตร (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)
        st.success("✅ โหลดเทมเพลตสำเร็จ")
    
    # 2. Font Management - ใหม่!
    st.subheader("🔤 จัดการฟอนต์")
    
    # เพิ่มฟอนต์ใหม่
    with st.expander("➕ เพิ่มฟอนต์ใหม่", expanded=True):
        new_font_file = st.file_uploader("เลือกไฟล์ฟอนต์ (.ttf)", type=['ttf'], key="new_font_uploader")
        new_font_name = st.text_input("ตั้งชื่อฟอนต์", placeholder="เช่น: THSarabun, THSarabunNew")
        
        if new_font_file and new_font_name:
            if st.button("✅ เพิ่มฟอนต์", use_container_width=True):
                try:
                    font_data = new_font_file.getvalue()
                    # ทดสอบโหลดฟอนต์
                    test_font = load_font(font_data, 20)
                    if test_font:
                        st.session_state.fonts[new_font_name] = {
                            'name': new_font_name,
                            'data': font_data,
                            'file_name': new_font_file.name
                        }
                        if new_font_name not in st.session_state.font_list:
                            st.session_state.font_list.append(new_font_name)
                        st.success(f"✅ เพิ่มฟอนต์ '{new_font_name}' สำเร็จ!")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ ไม่สามารถเพิ่มฟอนต์ได้: {e}")
    
    # แสดงฟอนต์ที่มี
    if st.session_state.fonts:
        st.markdown("**📋 ฟอนต์ที่มีอยู่:**")
        for font_name in list(st.session_state.fonts.keys()):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔤 {font_name}")
            if col2.button("🗑️", key=f"del_font_{font_name}"):
                del st.session_state.fonts[font_name]
                if font_name in st.session_state.font_list:
                    st.session_state.font_list.remove(font_name)
                st.rerun()
    else:
        st.info("💡 ยังไม่มีฟอนต์ที่อัปโหลด (ใช้ฟอนต์ระบบ)")
    
    # 3. Data
    data_file = st.file_uploader("📊 ข้อมูล (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    if data_file:
        try:
            if data_file.name.endswith('.csv'):
                st.session_state.data = pd.read_csv(data_file)
            else:
                st.session_state.data = pd.read_excel(data_file)
            st.success(f"✅ โหลดข้อมูลสำเร็จ: {len(st.session_state.data)} รายการ")
            st.dataframe(st.session_state.data.head(3))
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดข้อมูลได้: {e}")

if 'template' not in st.session_state:
    st.info("👈 กรุณาอัปโหลด 'ต้นแบบเกียรติบัตร' เพื่อเริ่มต้น")
    st.stop()

# --- MAIN AREA ---
st.header("2️⃣ กำหนดตำแหน่งข้อความ")

col_img, col_form = st.columns([1.5, 1])

with col_img:
    st.markdown("**🖱️ คลิกบนรูปเพื่อเลือกพิกัด**")
    
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
        st.success(f"📍 พิกัด: X={st.session_state.click_x}, Y={st.session_state.click_y}")

with col_form:
    st.markdown("**📝 เพิ่มข้อความ**")
    with st.form("add_text_form", clear_on_submit=False):
        t_type = st.radio("ชนิดข้อมูล", ["พิมพ์เอง", "ดึงจาก Excel"], horizontal=True)
        
        if "พิมพ์เอง" in t_type:
            t_val = st.text_input("ข้อความ", placeholder="พิมพ์ข้อความ")
            t_col = ""
        else:
            if 'data' in st.session_state:
                t_col = st.selectbox("เลือกคอลัมน์", st.session_state.data.columns)
                t_val = ""
                # แสดงตัวอย่างข้อมูล
                if t_col:
                    sample = st.session_state.data[t_col].iloc[0] if len(st.session_state.data) > 0 else ""
                    st.caption(f"📝 ตัวอย่าง: {sample}")
            else:
                st.warning("⚠️ กรุณาอัปโหลดไฟล์ข้อมูลก่อน")
                t_col = ""
                t_val = ""

        c1, c2 = st.columns(2)
        x_pos = c1.number_input("แกน X", value=st.session_state.click_x)
        y_pos = c2.number_input("แกน Y", value=st.session_state.click_y)
        
        f_size = st.slider("ขนาดฟอนต์", 10, 300, value=60, step=5)
        f_color = st.color_picker("สี", value="#000000")
        
        # เลือกฟอนต์ - อัปเดตให้แสดงฟอนต์ที่เพิ่มเข้ามา
        font_options = ['Default'] + st.session_state.font_list
        if not font_options:
            font_options = ['Default']
        selected_font = st.selectbox("เลือกฟอนต์", font_options, index=0)
        
        # แสดงตัวอย่างการปรับขนาด
        if t_val or t_col:
            preview_text = t_val if t_type == "พิมพ์เอง" else f"ตัวอย่าง: {t_col}"
            st.caption(f"🔤 {preview_text} (ขนาด {f_size})")
        
        if st.form_submit_button("➕ เพิ่มข้อความ", type="primary"):
            if t_type == "พิมพ์เอง" and not t_val:
                st.warning("⚠️ กรุณาพิมพ์ข้อความ")
            elif t_type == "ดึงจาก Excel" and not t_col:
                st.warning("⚠️ กรุณาเลือกคอลัมน์")
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

# --- พรีวิว ---
st.header("3️⃣ ดูตัวอย่าง")

if st.session_state.texts:
    # แสดงรายการข้อความ
    st.subheader("📋 รายการข้อความทั้งหมด")
    for i, t in enumerate(st.session_state.texts):
        lbl = t['text'] if t['type'] == 'static' else f"📊 {t['column']}"
        font_display = t.get('font_name', 'Default')
        
        col1, col2, col3 = st.columns([4, 2, 0.5])
        col1.write(f"**{i+1}. {lbl}**")
        col2.write(f"ขนาด: {t['size']} | ฟอนต์: {font_display} | ({t['x']}, {t['y']})")
        if col3.button("🗑️", key=f"del_{i}"):
            st.session_state.texts.pop(i)
            st.rerun()
    
    # แสดงตัวอย่าง
    st.subheader("👁️ ตัวอย่างผลลัพธ์")
    preview_row = None
    if 'data' in st.session_state and len(st.session_state.data) > 0:
        row_idx = st.number_input("ดูตัวอย่างแถวที่:", 0, max(0, len(st.session_state.data)-1), 0, step=1)
        preview_row = st.session_state.data.iloc[row_idx].to_dict()
    
    try:
        preview_img = render_certificate(st.session_state.template, st.session_state.texts, preview_row)
        st.image(preview_img, width=650)
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
else:
    st.info("💡 เริ่มต้นด้วยการเพิ่มข้อความด้านบน")

# --- Export ---
if 'data' in st.session_state and st.session_state.texts:
    st.markdown("---")
    st.header("4️⃣ สร้างไฟล์")
    
    col1, col2 = st.columns(2)
    with col1:
        filename_col = st.selectbox("เลือกคอลัมน์ชื่อไฟล์", st.session_state.data.columns)
    with col2:
        fix_thai = st.checkbox("แก้ไขสระ/วรรณยุกต์", value=True)
    
    if st.button("🚀 สร้าง ZIP", type="primary", use_container_width=True):
        zip_buffer = BytesIO()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("กำลังสร้าง..."):
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                total = len(st.session_state.data)
                for idx, row in st.session_state.data.iterrows():
                    status_text.text(f"กำลังสร้าง: {idx+1}/{total}")
                    
                    texts_to_render = st.session_state.texts.copy()
                    if fix_thai:
                        for txt in texts_to_render:
                            if txt['type'] == 'static':
                                txt['text'] = fix_thai_text(txt['text'])
                    
                    final_img = render_certificate(st.session_state.template, texts_to_render, row.to_dict())
                    img_io = BytesIO()
                    final_img.save(img_io, format="PNG", optimize=True)
                    clean_name = sanitize_filename(row[filename_col])
                    zf.writestr(f"{clean_name}.png", img_io.getvalue())
                    
                    progress_bar.progress((idx + 1) / total)
            
            status_text.text("✅ เสร็จสิ้น!")
            st.success("🎉 สร้างไฟล์ทั้งหมดสำเร็จ!")
            st.download_button(
                "📥 ดาวน์โหลด ZIP",
                zip_buffer.getvalue(),
                "certificates.zip",
                "application/zip",
                use_container_width=True
            )
