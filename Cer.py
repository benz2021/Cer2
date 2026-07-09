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

# ตัวแปรเก็บฟอนต์ที่โหลดแล้ว
_font_cache = {}

def get_font_path():
    """ค้นหาฟอนต์ในระบบที่สามารถปรับขนาดได้"""
    font_paths = [
        # Windows
        'C:\\Windows\\Fonts\\Arial.ttf',
        'C:\\Windows\\Fonts\\Tahoma.ttf',
        'C:\\Windows\\Fonts\\msyh.ttc',
        'C:\\Windows\\Fonts\\Angsana.ttf',
        'C:\\Windows\\Fonts\\Cordia.ttf',
        # Linux
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
        # macOS
        '/System/Library/Fonts/Helvetica.ttf',
        '/System/Library/Fonts/Arial.ttf',
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None

def load_font_from_bytes(font_data, size):
    """โหลดฟอนต์จากข้อมูล bytes"""
    cache_key = f"{hash(font_data)}_{size}"
    
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    
    tmp_path = None # Initialize tmp_path
    try:
        # สร้างไฟล์ชั่วคราว
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.ttf')
        try:
            tmp_file.write(font_data)
            tmp_file.close() # ปิดไฟล์ก่อนโหลดด้วย ImageFont.truetype
            tmp_path = tmp_file.name
        
            # โหลดฟอนต์
            font = ImageFont.truetype(tmp_path, size)
            
            # เก็บใน cache
            _font_cache[cache_key] = font
            
            return font
        finally:
            # ลบไฟล์ชั่วคราวเสมอ ไม่ว่าจะเกิดข้อผิดพลาดหรือไม่
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception as e:
        st.warning(f"ไม่สามารถโหลดฟอนต์: {e}")
        return None

def get_font(font_name, size):
    """ดึงฟอนต์ตามชื่อและขนาด"""
    # ถ้าเป็น Default หรือไม่มีฟอนต์ในระบบ
    if font_name == 'Default' or not font_name:
        # ใช้ฟอนต์ระบบ
        system_font = get_font_path()
        if system_font:
            try:
                cache_key = f"system_{size}"
                if cache_key not in _font_cache:
                    _font_cache[cache_key] = ImageFont.truetype(system_font, size)
                return _font_cache[cache_key]
            except:
                pass
        # ถ้าไม่มี ให้ลองใช้ฟอนต์เริ่มต้นของ PIL (อาจไม่รองรับภาษาไทย)
        try:
            default_font = ImageFont.load_default()
            st.warning("⚠️ ไม่พบฟอนต์ระบบที่เหมาะสม หรือฟอนต์ที่อัปโหลดไม่สามารถโหลดได้ กำลังใช้ฟอนต์เริ่มต้นของ PIL (อาจไม่รองรับภาษาไทย)")
            return default_font
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดฟอนต์เริ่มต้นของ PIL ได้: {e}")
            return None
    
    # โหลดจากฟอนต์ที่ผู้ใช้เพิ่ม
    if font_name in st.session_state.fonts:
        font_data = st.session_state.fonts[font_name]['data']
        font = load_font_from_bytes(font_data, size)
        if font:
            return font
    
    # ถ้าไม่เจอ ให้ใช้ฟอนต์ระบบ
    system_font = get_font_path()
    if system_font:
        try:
            cache_key = f"system_{size}"
            if cache_key not in _font_cache:
                _font_cache[cache_key] = ImageFont.truetype(system_font, size)
            return _font_cache[cache_key]
        except:
            pass
    
    # หากไม่พบฟอนต์ที่ผู้ใช้เพิ่ม หรือฟอนต์ระบบ ให้ใช้ฟอนต์เริ่มต้นของ PIL
    st.warning("⚠️ ไม่พบฟอนต์ที่ระบุ กำลังใช้ฟอนต์เริ่มต้นของ PIL (อาจไม่รองรับภาษาไทย)")
    return ImageFont.load_default()

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
        font = get_font(font_name, txt['size'])
        
        if font is None:
            font = ImageFont.load_default()
        
        try:
            # วัดความกว้างข้อความ
            # สำหรับภาษาไทย ควรใช้การจัดตำแหน่งแบบปกติ หรือใช้ไลบรารีที่รองรับการจัดตำแหน่งภาษาไทยโดยเฉพาะ
            # หากต้องการจัดกึ่งกลาง สามารถคำนวณ text_width และปรับ start_x ได้เอง
            text_bbox = draw.textbbox((0, 0), content, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            start_x = txt['x'] - (text_width / 2)
            draw.text((start_x, txt['y']), content, fill=txt['color'], font=font)
        except Exception as e:
            # Fallback สำหรับกรณีที่เกิดข้อผิดพลาดในการเรนเดอร์
            draw.text((txt['x'], txt['y']), content, fill=txt['color'], font=font)
    
    return img

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', str(name)).strip() or "certificate"

# ==========================================
# 🎨 UI - STREAMLIT APP
# ==========================================
st.set_page_config(page_title="Auto Cert Pro", layout="wide")

# ตั้งค่า Session State
if "click_x" not in st.session_state: st.session_state.click_x = 0
if "click_y" not in st.session_state: st.session_state.click_y = 0
if 'texts' not in st.session_state: st.session_state.texts = []
if 'fonts' not in st.session_state: st.session_state.fonts = {}
if 'font_names' not in st.session_state: st.session_state.font_names = []

st.title("🎓 Certificate Generator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📁 1️⃣ อัปโหลดไฟล์")
    
    # Template
    template_file = st.file_uploader("📄 พื้นหลังเกียรติบัตร", type=['jpg', 'jpeg', 'png'])
    if template_file:
        st.session_state.template = Image.open(template_file)
        st.success("✅ โหลดเทมเพลตสำเร็จ")
    
    # Data
    data_file = st.file_uploader("📊 ข้อมูลรายชื่อ (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    if data_file:
        try:
            if data_file.name.endswith('.csv'):
                st.session_state.data = pd.read_csv(data_file)
            else:
                st.session_state.data = pd.read_excel(data_file)
            st.success(f"✅ โหลดข้อมูลสำเร็จ: {len(st.session_state.data)} รายการ")
            with st.expander("ดูตัวอย่างข้อมูล"):
                st.dataframe(st.session_state.data.head(5))
        except Exception as e:
            st.error(f"❌ ไม่สามารถโหลดข้อมูลได้: {e}")
    
    st.divider()
    
    # --- จัดการฟอนต์ ---
    st.header("🔤 2️⃣ จัดการฟอนต์")
    
    # เพิ่มฟอนต์ใหม่
    with st.expander("➕ เพิ่มฟอนต์ใหม่", expanded=True):
        st.info("อัปโหลดไฟล์ฟอนต์ .ttf เพื่อใช้ในเกียรติบัตร")
        
        new_font_file = st.file_uploader("เลือกไฟล์ฟอนต์ (.ttf)", type=['ttf'], key="new_font")
        new_font_name = st.text_input("ชื่อฟอนต์", placeholder="เช่น: THSarabun, THSarabunNew")
        
        if new_font_file and new_font_name:
            if st.button("✅ เพิ่มฟอนต์", use_container_width=True):
                try:
                    font_data = new_font_file.getvalue()
                    # ทดสอบโหลดฟอนต์
                    test_font = load_font_from_bytes(font_data, 20)
                    if test_font:
                        st.session_state.fonts[new_font_name] = {
                            'name': new_font_name,
                            'data': font_data,
                            'file_name': new_font_file.name
                        }
                        if new_font_name not in st.session_state.font_names:
                            st.session_state.font_names.append(new_font_name)
                        st.success(f"✅ เพิ่มฟอนต์ '{new_font_name}' สำเร็จ!")
                        st.rerun()
                    else:
                        st.error("❌ ไฟล์ไม่ใช่ฟอนต์ที่ถูกต้อง")
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
    
    # แสดงฟอนต์ที่มี
    if st.session_state.font_names:
        st.markdown("**📋 ฟอนต์ที่มีอยู่:**")
        for font_name in st.session_state.font_names.copy():
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔤 {font_name}")
            if col2.button("🗑️", key=f"del_{font_name}"):
                del st.session_state.fonts[font_name]
                st.session_state.font_names.remove(font_name)
                st.rerun()
    else:
        st.info("💡 ยังไม่มีฟอนต์เพิ่ม (ใช้ฟอนต์ระบบ 'Default')")

if 'template' not in st.session_state:
    st.info("👈 กรุณาอัปโหลด 'พื้นหลังเกียรติบัตร' เพื่อเริ่มต้น")
    st.stop()

# --- MAIN AREA ---
st.header("📍 3️⃣ กำหนดตำแหน่งและเพิ่มข้อความ")

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

    coords = streamlit_image_coordinates(display_img, key="click_image")
    
    if coords is not None:
        st.session_state.click_x = int(coords['x'] * ratio)
        st.session_state.click_y = int(coords['y'] * ratio)
        st.success(f"📍 พิกัด: X={st.session_state.click_x}, Y={st.session_state.click_y}")

with col_form:
    st.markdown("**✏️ เพิ่มข้อความ**")
    
    with st.form("add_text", clear_on_submit=False):
        # ประเภทข้อความ
        text_type = st.radio("ประเภท", ["พิมพ์เอง", "จาก Excel"], horizontal=True)
        
        if text_type == "พิมพ์เอง":
            text_content = st.text_input("ข้อความ", placeholder="พิมพ์ข้อความที่ต้องการ")
            selected_column = ""
        else:
            if 'data' in st.session_state:
                selected_column = st.selectbox("เลือกคอลัมน์", st.session_state.data.columns)
                if selected_column:
                    sample = st.session_state.data[selected_column].iloc[0] if len(st.session_state.data) > 0 else ""
                    st.caption(f"📝 ตัวอย่าง: {sample}")
                text_content = ""
            else:
                st.warning("⚠️ กรุณาอัปโหลดไฟล์ข้อมูลก่อน")
                selected_column = ""
                text_content = ""
        
        # พิกัด
        col_x, col_y = st.columns(2)
        x_pos = col_x.number_input("X", value=st.session_state.click_x)
        y_pos = col_y.number_input("Y", value=st.session_state.click_y)
        
        # ขนาดฟอนต์
        font_size = st.slider("ขนาดฟอนต์", 10, 500, value=60, step=5)
        
        # สี
        font_color = st.color_picker("สี", value="#000000")
        
        # เลือกฟอนต์ - แสดงฟอนต์ทั้งหมดที่เพิ่มเข้ามา
        font_options = ['Default'] + st.session_state.font_names
        selected_font = st.selectbox("เลือกฟอนต์", font_options, index=0)
        
        # แสดงตัวอย่างการปรับขนาด
        preview_text = text_content if text_type == "พิมพ์เอง" else selected_column
        if preview_text:
            st.caption(f"🔤 ตัวอย่าง: '{preview_text}' ขนาด {font_size}px")
        
        if st.form_submit_button("➕ เพิ่มข้อความ", type="primary"):
            if text_type == "พิมพ์เอง" and not text_content:
                st.warning("⚠️ กรุณาพิมพ์ข้อความ")
            elif text_type == "จาก Excel" and not selected_column:
                st.warning("⚠️ กรุณาเลือกคอลัมน์")
            else:
                st.session_state.texts.append({
                    'type': 'static' if text_type == "พิมพ์เอง" else 'excel',
                    'text': text_content,
                    'column': selected_column,
                    'x': x_pos,
                    'y': y_pos,
                    'size': font_size,
                    'color': font_color,
                    'font_name': selected_font
                })
                st.success("✅ เพิ่มข้อความสำเร็จ!")
                st.rerun()

st.divider()

# --- แสดงข้อความที่เพิ่มแล้ว ---
st.header("📋 4️⃣ จัดการข้อความ")

if st.session_state.texts:
    # แสดงรายการข้อความทั้งหมด
    for i, txt in enumerate(st.session_state.texts):
        label = txt['text'] if txt['type'] == 'static' else f"📊 {txt['column']}"
        font_name = txt.get('font_name', 'Default')
        
        with st.container():
            col1, col2, col3 = st.columns([4, 3, 1])
            col1.write(f"**{i+1}. {label}**")
            col2.write(f"ขนาด: {txt['size']}px | ฟอนต์: {font_name} | พิกัด: ({txt['x']}, {txt['y']})")
            if col3.button("🗑️", key=f"del_{i}"):
                st.session_state.texts.pop(i)
                st.rerun()
    
    # แสดงตัวอย่าง
    st.subheader("👁️ ตัวอย่างเกียรติบัตร")
    
    preview_row = None
    if 'data' in st.session_state and len(st.session_state.data) > 0:
        row_idx = st.number_input(
            "เลือกแถวตัวอย่าง",
            min_value=0,
            max_value=len(st.session_state.data)-1,
            value=0,
            step=1
        )
        preview_row = st.session_state.data.iloc[row_idx].to_dict()
        
        # แสดงข้อมูล
        with st.expander("📊 ข้อมูลแถวนี้"):
            st.json(preview_row)
    
    try:
        preview_img = render_certificate(st.session_state.template, st.session_state.texts, preview_row)
        st.image(preview_img, width=700)
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการแสดงตัวอย่าง: {e}")
else:
    st.info("💡 ยังไม่มีข้อความ เพิ่มข้อความจากส่วนด้านบน")

# --- สร้างไฟล์ ---
if 'data' in st.session_state and st.session_state.texts:
    st.divider()
    st.header("📦 5️⃣ สร้างไฟล์ทั้งหมด")
    
    col1, col2 = st.columns(2)
    with col1:
        name_column = st.selectbox("เลือกคอลัมน์ชื่อไฟล์", st.session_state.data.columns)

    
    if st.button("🚀 สร้างไฟล์ ZIP", type="primary", use_container_width=True):
        zip_buffer = BytesIO()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner("กำลังสร้างเกียรติบัตร..."):
                with zipfile.ZipFile(zip_buffer, 'w') as zf:
                    total = len(st.session_state.data)
                    for idx, row in st.session_state.data.iterrows():
                        status_text.text(f"กำลังสร้าง: {idx+1}/{total}")
                        
                        texts_to_render = st.session_state.texts.copy()
                        
                        final_img = render_certificate(st.session_state.template, texts_to_render, row.to_dict())
                        img_io = BytesIO()
                        final_img.save(img_io, format="PNG", optimize=True)
                        
                        clean_name = sanitize_filename(row[name_column])
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
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด: {e}")
            status_text.text("❌ ล้มเหลว")
