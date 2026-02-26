import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import io

# ==========================================
# 1. 核心配置与云数据库连接
# ==========================================
# 本地测试时，直接把字符串赋给变量（注意两边要有引号）
SUPABASE_URL = "https://lwxlyinekziylfujscqd.supabase.co"
SUPABASE_KEY = "sb_publishable_Sia-RhW-wApZ1McliX_cjw_K4iOw5MA"

@st.cache_resource
def init_connection():
    """初始化数据库连接，使用缓存避免重复连接"""
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"⚠️ 云数据库连接初始化失败: {e}")
        return None

supabase = init_connection()

# ==========================================
# 2. 页面全局配置
# ==========================================
st.set_page_config(
    page_title="储罐焊接数字化管理平台",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入 CSS 样式以优化手机端显示
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# 侧边栏导航
st.sidebar.title("🚧 施工现场管理")
menu = st.sidebar.selectbox(
    "功能切换", 
    ["👷 工人现场填报", "🖥️ 管理后台监控", "⚙️ 任务/参数布置"]
)

# ==========================================
# 3. 功能模块：工人现场填报 (极简操作设计)
# ==========================================
if menu == "工人现场填报":
    st.header("📲 焊接数据实时上传")
    
    # 动态获取后端配置的选项
    try:
        cfg_res = supabase.table("weld_configs").select("*").execute()
        welders = [r['value'] for r in cfg_res.data if r['type'] == '焊工']
        weld_nos = [r['value'] for r in cfg_res.data if r['type'] == '焊缝号']
    except Exception as e:
        st.error("无法获取配置信息，请检查网络连接。")
        st.stop()

    if not welders or not weld_nos:
        st.warning("⚠️ 管理员尚未布置焊工名单或焊缝编号，请联系后台。")
    
    # 填报表单
    with st.form("weld_submission_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            welder_name = st.selectbox("🙋 您的姓名", options=welders)
        with col2:
            weld_id = st.selectbox("🆔 焊缝编号", options=weld_nos)
        
        # 核心：调用手机相机
        photo_file = st.camera_input("📷 拍摄焊后质量照片")
        
        extra_info = st.text_area(
            "⚠️ 异常备注/额外数据", 
            placeholder="如：环境风力大、坡口不齐、间隙过大等。填写后将触发红色预警！"
        )
        
        submitted = st.form_submit_button("🚀 立即上传并开始下一行")

        if submitted:
            if not welder_name or not weld_id:
                st.error("请完整填写姓名和编号！")
            else:
                try:
                    photo_url = ""
                    # 处理照片上传到存储桶
                    if photo_file:
                        with st.spinner("正在同步照片至云端..."):
                            fname = f"weld_{int(time.time())}_{welder_name}.jpg"
                            # 确保存储桶名称为 weld-photos 且设为 Public
                            supabase.storage.from_("weld-photos").upload(fname, photo_file.getvalue())
                            photo_url = supabase.storage.from_("weld-photos").get_public_url(fname)

                    # 健壮性逻辑：判定警告状态
                    is_alert = True if extra_info.strip() else False
                    
                    # 写入数据记录
                    payload = {
                        "welder": welder_name,
                        "weld_no": weld_id,
                        "extra_note": extra_info,
                        "photo_url": photo_url,
                        "is_alert": is_alert,
                        "audit_status": "🔴 待人工审核" if is_alert else "🟢 自动通过"
                    }
                    
                    supabase.table("weld_records").insert(payload).execute()
                    st.success(f"✅ 焊缝 {weld_id} 提交成功！")
                    st.toast("数据已同步", icon="✔️")
                    time.sleep(1)
                    st.rerun() # 自动刷新进入下一行录入
                except Exception as ex:
                    st.error(f"数据提交失败: {ex}")

# ==========================================
# 4. 功能模块：管理后台监控 (连锁预警逻辑)
# ==========================================
elif menu == "管理后台监控":
    st.header("🖥️ 质量监控与人工判定后台")
    
    # 获取数据
    res = supabase.table("weld_records").select("*").order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        
        # 顶部指标卡
        m1, m2, m3 = st.columns(3)
        m1.metric("累计焊缝数", len(df))
        alert_df = df[df['is_alert'] == True]
        m2.metric("待处理预警", len(alert_df), delta=len(alert_df), delta_color="inverse")
        m3.metric("最后更新", datetime.now().strftime("%H:%M:%S"))

        # --- 重点：预警审核区 ---
        if not alert_df.empty:
            st.subheader("🚨 实时异常预警（需人工介入）")
            for _, row in alert_df.iterrows():
                with st.expander(f"⚠️ 预警确认：{row['weld_no']} (焊工: {row['welder']})", expanded=True):
                    c_img, c_txt, c_btn = st.columns([1, 2, 1])
                    with c_img:
                        if row['photo_url']:
                            st.image(row['photo_url'], use_container_width=True)
                        else:
                            st.write("现场未传照片")
                    with c_txt:
                        st.error(f"**现场异常描述：**\n\n{row['extra_note']}")
                        st.caption(f"上报时间: {row['created_at']}")
                    with c_btn:
                        st.write("人工判定合理性:")
                        if st.button("✅ 判定合理", key=f"pass_{row['id']}"):
                            supabase.table("weld_records").update({"audit_status": "🔵 已人工通过", "is_alert": False}).eq("id", row['id']).execute()
                            st.rerun()
                        if st.button("❌ 驳回纠偏", key=f"fail_{row['id']}"):
                            supabase.table("weld_records").update({"audit_status": "🚫 已驳回", "is_alert": False}).eq("id", row['id']).execute()
                            st.rerun()
# 在管理后台监控模块中
if res.data:
    df = pd.DataFrame(res.data)
    
    # 按照重要性排序显示的列（可以自定义）
    display_order = [
        'weld_date', 'area', 'drawing_no', 'weld_no', 
        'welder_code', 'team_leader', 'audit_status'
    ]
    
    st.subheader("📊 实时施工概览")
    # 只显示关键核心字段，避免页面太宽
    st.dataframe(df[display_order], use_container_width=True)
    
    # 详情查看器：点击某一行查看完整 15+ 字段
    st.info("💡 提示：点击下方表格中的具体行，或直接导出 Excel 查看完整 15 项参数。")
    
    # 下载按钮
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button(
        label="📥 导出全要素焊接记录 (Excel)",
        data=buffer.getvalue(),
        file_name=f"焊接质量档案_{datetime.now().strftime('%Y%m%d')}.xlsx"
    )
    
        # --- 全量历史档案 ---
        st.divider()
        st.subheader("📂 完整施工记录档案")
        st.dataframe(df, use_container_width=True)
        
        # 导出 Excel 功能
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        st.download_button(
            label="📥 导出全量记录为 Excel",
            data=buffer.getvalue(),
            file_name=f"储罐记录_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("暂无提交数据记录。")

# ==========================================
# 5. 功能模块：任务/参数布置
# ==========================================
elif menu == "任务/参数布置":
    st.header("⚙️ 施工参数布置中心")
    st.markdown("在此设置的内容将同步到工人的下拉选项中，防止手动输入错误。")
    
    t1, t2 = st.tabs(["➕ 新增选项", "📋 当前配置"])
    
    with t1:
        col_type, col_val = st.columns(2)
        with col_type:
            opt_type = st.radio("设置类型", ["焊工", "焊缝号"])
        with col_val:
            opt_val = st.text_input("输入具体名称/编号 (如: 李工 或 TK-501)")
            
        if st.button("确认同步"):
            if opt_val:
                supabase.table("weld_configs").insert({"type": opt_type, "value": opt_val}).execute()
                st.success(f"已同步 {opt_type}: {opt_val}")
                st.rerun()
    
    with t2:
        cfg_data = supabase.table("weld_configs").select("*").execute()
        if cfg_data.data:

            st.table(pd.DataFrame(cfg_data.data)[['type', 'value']])





