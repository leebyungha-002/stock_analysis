import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import OpenDartReader
import FinanceDataReader as fdr
import io
from datetime import datetime

# 페이지 설정
st.set_page_config(
    page_title="DART XBRL 데이터 분석",
    page_icon="📊",
    layout="wide"
)

# 세션 상태 초기화
if 'dart' not in st.session_state:
    st.session_state.dart = None
if 'api_key' not in st.session_state:
    st.session_state.api_key = None
if 'financial_data' not in st.session_state:
    st.session_state.financial_data = None

# ==========================================
# 🔧 유틸리티 함수
# ==========================================

def clean_numeric_value(value):
    """
    문자열을 숫자로 안전하게 변환하는 함수
    - 천 단위 콤마 제거
    - 빈 문자열, None 처리
    - 숫자가 아닌 값은 0으로 반환
    """
    if pd.isna(value) or value is None:
        return 0.0
    
    # 문자열로 변환
    if isinstance(value, str):
        # 콤마 제거
        value = value.replace(',', '').strip()
        # 빈 문자열 체크
        if value == '' or value == '-':
            return 0.0
        # 숫자 변환 시도
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    # 이미 숫자인 경우
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def format_currency(value, unit='억원'):
    """
    숫자를 통화 형식으로 포맷팅
    """
    if pd.isna(value) or value == 0:
        return '-'
    
    if unit == '억원':
        if abs(value) >= 10000:
            return f"{value/10000:.2f} 조원"
        else:
            return f"{value:.2f} 억원"
    elif unit == '조원':
        return f"{value:.2f} 조원"
    else:
        return f"{value:,.0f}"

def preprocess_financial_data(df):
    """
    재무제표 데이터 전처리 함수
    - 금액 컬럼의 천 단위 콤마 제거
    - 문자열을 숫자형으로 변환
    - 원 단위를 억원 단위로 변환 (선택 사항)
    
    Args:
        df: 원본 재무제표 DataFrame
    
    Returns:
        전처리된 DataFrame
    """
    if df is None or df.empty:
        return df
    
    df_processed = df.copy()
    
    # 금액 관련 컬럼 찾기
    amount_columns = []
    for col in df_processed.columns:
        if 'amount' in col.lower() or '금액' in col or 'thstrm' in col.lower() or 'frmtrm' in col.lower():
            amount_columns.append(col)
    
    # 각 금액 컬럼에 대해 전처리 수행
    for col in amount_columns:
        if col in df_processed.columns:
            try:
                # 1. 문자열로 변환 후 콤마 제거
                df_processed[col] = df_processed[col].astype(str).str.replace(',', '', regex=False)
                
                # 2. 숫자형으로 강제 변환 (변환 안 되는 값은 NaN)
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
                
                # 3. NaN을 0으로 채우기
                df_processed[col] = df_processed[col].fillna(0)
                
                # 4. 원 단위를 억원 단위로 변환 (1억 = 100,000,000)
                # 단위가 너무 크면 보기 어려우므로 억원 단위로 변환
                df_processed[col] = df_processed[col] / 100000000
                
            except Exception as e:
                st.warning(f"⚠️ 컬럼 '{col}' 전처리 중 오류 발생: {str(e)}")
                continue
    
    return df_processed

# ==========================================
# 📊 재무비율 계산 함수 (연도별)
# ==========================================

def calculate_financial_ratios_by_year(df):
    """
    재무제표 데이터에서 연도별 재무비율을 계산하는 함수
    
    Returns:
        DataFrame: 연도별 재무비율 데이터 (귀속년도, 회사명, 각종 비율)
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # 필요한 컬럼 확인
    required_cols = ['회사명', '귀속년도', 'account_nm', 'thstrm_amount']
    if not all(col in df.columns for col in required_cols):
        st.warning("⚠️ 재무제표 데이터 형식이 올바르지 않습니다.")
        return pd.DataFrame()
    
    ratios_list = []
    companies = df['회사명'].unique()
    years = sorted(df['귀속년도'].unique())
    
    for company in companies:
        company_data = df[df['회사명'] == company].copy()
        
        for year in years:
            year_data = company_data[company_data['귀속년도'] == year].copy()
            
            if year_data.empty:
                continue
            
            # 계정명을 키로 하는 딕셔너리 생성
            account_dict = {}
            for _, row in year_data.iterrows():
                account_name = str(row['account_nm']).strip()
                # 이미 전처리된 데이터이므로 직접 숫자로 변환 시도
                try:
                    amount = float(row['thstrm_amount']) if pd.notna(row['thstrm_amount']) else 0
                except (ValueError, TypeError):
                    amount = clean_numeric_value(row['thstrm_amount'])
                account_dict[account_name] = amount
            
            # 전년도 데이터 수집 (매출액 증가율 계산용)
            prev_year = year - 1
            prev_year_data = company_data[company_data['귀속년도'] == prev_year].copy()
            account_dict_prev = {}
            if not prev_year_data.empty:
                for _, row in prev_year_data.iterrows():
                    account_name = str(row['account_nm']).strip()
                    try:
                        amount = float(row['thstrm_amount']) if pd.notna(row['thstrm_amount']) else 0
                    except (ValueError, TypeError):
                        amount = clean_numeric_value(row['thstrm_amount'])
                    account_dict_prev[account_name] = amount
            
            # 재무비율 계산
            ratios = {
                '회사명': company,
                '귀속년도': year
            }
            
            # 수익성 지표
            # 영업이익률 = (영업이익 / 매출액) * 100
            try:
                operating_profit = account_dict.get('영업이익', 0) or account_dict.get('영업손익', 0)
                revenue = account_dict.get('매출액', 0) or account_dict.get('수익(매출액)', 0)
                if revenue != 0:
                    ratios['영업이익률(%)'] = round((operating_profit / revenue) * 100, 2)
                else:
                    ratios['영업이익률(%)'] = None
            except:
                ratios['영업이익률(%)'] = None
            
            # 순이익률 = (당기순이익 / 매출액) * 100
            try:
                net_income = account_dict.get('당기순이익', 0) or account_dict.get('당기순손익', 0)
                revenue = account_dict.get('매출액', 0) or account_dict.get('수익(매출액)', 0)
                if revenue != 0:
                    ratios['순이익률(%)'] = round((net_income / revenue) * 100, 2)
                else:
                    ratios['순이익률(%)'] = None
            except:
                ratios['순이익률(%)'] = None
            
            # 안정성 지표
            # 부채비율 = (부채총계 / 자본총계) * 100
            try:
                total_debt = account_dict.get('부채총계', 0) or account_dict.get('부채', 0)
                total_equity = account_dict.get('자본총계', 0) or account_dict.get('자본', 0)
                if total_equity != 0:
                    ratios['부채비율(%)'] = round((total_debt / total_equity) * 100, 2)
                else:
                    ratios['부채비율(%)'] = None
            except:
                ratios['부채비율(%)'] = None
            
            # 유동비율 = (유동자산 / 유동부채) * 100
            try:
                current_assets = account_dict.get('유동자산', 0) or account_dict.get('유동자산합계', 0)
                current_liabilities = account_dict.get('유동부채', 0) or account_dict.get('유동부채합계', 0)
                if current_liabilities != 0:
                    ratios['유동비율(%)'] = round((current_assets / current_liabilities) * 100, 2)
                else:
                    ratios['유동비율(%)'] = None
            except:
                ratios['유동비율(%)'] = None
            
            # 성장성 지표
            # 매출액 증가율 = ((당기 매출액 - 전기 매출액) / 전기 매출액) * 100
            try:
                revenue_current = account_dict.get('매출액', 0) or account_dict.get('수익(매출액)', 0)
                revenue_prev = account_dict_prev.get('매출액', 0) or account_dict_prev.get('수익(매출액)', 0)
                if revenue_prev != 0:
                    ratios['매출액증가율(%)'] = round(((revenue_current - revenue_prev) / revenue_prev) * 100, 2)
                else:
                    ratios['매출액증가율(%)'] = None
            except:
                ratios['매출액증가율(%)'] = None
            
            ratios_list.append(ratios)
    
    return pd.DataFrame(ratios_list)

# ==========================================
# 📈 시각화 함수 (연도별 추이)
# ==========================================

def create_trend_chart(df):
    """
    연도별 재무제표 추이를 시각화하는 함수
    
    Args:
        df: 재무제표 DataFrame (귀속년도 컬럼 포함)
    
    Returns:
        plotly figure 객체
    """
    if df is None or df.empty:
        return None
    
    # 필요한 컬럼 확인
    if '회사명' not in df.columns or '귀속년도' not in df.columns or 'account_nm' not in df.columns:
        return None
    
    # 회사명 (1개만)
    companies = df['회사명'].unique()
    if len(companies) == 0:
        return None
    
    company = companies[0]  # 첫 번째 회사만 사용
    company_data = df[df['회사명'] == company].copy()
    
    # 연도 정렬
    years = sorted(company_data['귀속년도'].unique())
    
    # 서브플롯 생성 (2개 행, 1개 열)
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('매출액 & 영업이익 추이 (억원)', '부채비율 추이 (%)'),
        vertical_spacing=0.15,
        shared_xaxes=True
    )
    
    # 매출액과 영업이익 데이터 수집
    revenue_values = []
    operating_profit_values = []
    debt_ratio_values = []
    
    for year in years:
        year_data = company_data[company_data['귀속년도'] == year].copy()
        
        revenue = 0
        operating_profit = 0
        total_debt = 0
        total_equity = 0
        debt_ratio = None
        
        # 계정별로 데이터 수집
        for _, row in year_data.iterrows():
            account_name = str(row['account_nm']).strip()
            # 이미 전처리된 데이터이므로 직접 숫자로 변환 시도
            try:
                amount = float(row.get('thstrm_amount', 0)) if pd.notna(row.get('thstrm_amount')) else 0
            except (ValueError, TypeError):
                amount = clean_numeric_value(row.get('thstrm_amount', 0))
            
            if account_name == '매출액' or account_name == '수익(매출액)':
                revenue = amount
            elif account_name == '영업이익' or account_name == '영업손익':
                operating_profit = amount
            elif account_name == '부채총계' or account_name == '부채':
                total_debt = amount
            elif account_name == '자본총계' or account_name == '자본':
                total_equity = amount
        
        # 부채비율 계산
        if total_equity != 0:
            debt_ratio = (total_debt / total_equity) * 100
        
        revenue_values.append(revenue)
        operating_profit_values.append(operating_profit)
        debt_ratio_values.append(debt_ratio)
    
    # 매출액 & 영업이익 차트
    fig.add_trace(
        go.Scatter(
            x=years,
            y=revenue_values,
            mode='lines+markers',
            name='매출액',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=10)
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=years,
            y=operating_profit_values,
            mode='lines+markers',
            name='영업이익',
            line=dict(color='#ff7f0e', width=3, dash='dash'),
            marker=dict(size=10)
        ),
        row=1, col=1
    )
    
    # 부채비율 차트
    if any(v is not None for v in debt_ratio_values):
        fig.add_trace(
            go.Scatter(
                x=years,
                y=debt_ratio_values,
                mode='lines+markers',
                name='부채비율',
                line=dict(color='#2ca02c', width=3),
                marker=dict(size=10)
            ),
            row=2, col=1
        )
    
    # 레이아웃 업데이트
    fig.update_layout(
        height=700,
        title_text=f"{company} 재무제표 추이 분석",
        title_x=0.5,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    fig.update_xaxes(title_text="연도", row=2, col=1)
    fig.update_yaxes(title_text="금액 (억원)", row=1, col=1)
    fig.update_yaxes(title_text="비율 (%)", row=2, col=1)
    
    return fig

# ==========================================
# 📋 KRX 주식 리스트 캐싱
# ==========================================

@st.cache_data
def get_stock_list_v3():
    """KOSPI, KOSDAQ 주식 리스트를 각각 가져와서 통합하는 함수"""
    try:
        kospi = fdr.StockListing('KOSPI')
        kospi['Market'] = 'KOSPI'
        
        kosdaq = fdr.StockListing('KOSDAQ')
        kosdaq['Market'] = 'KOSDAQ'
        
        combined_df = pd.concat([kospi, kosdaq])
        return combined_df
    except Exception as e:
        return None

# ==========================================
# 🎨 사이드바 - API 키 입력 및 조회 설정
# ==========================================

with st.sidebar:
    st.header("🔐 DART API 인증")
    st.markdown("---")
    
    api_key_input = st.text_input(
        "DART API 키",
        type="password",
        value=st.session_state.api_key if st.session_state.api_key else "",
        help="금융감독원 DART에서 발급받은 API 키를 입력하세요."
    )
    
    if st.button("인증", type="primary", use_container_width=True):
        if api_key_input:
            try:
                if api_key_input.strip():
                    dart = OpenDartReader(api_key_input.strip())
                    if dart is not None:
                        st.session_state.dart = dart
                        st.session_state.api_key = api_key_input.strip()
                        st.success("✅ API 인증이 완료되었습니다!")
                    else:
                        st.error("❌ 인증 실패: OpenDartReader 객체를 생성할 수 없습니다.")
                        st.session_state.dart = None
                else:
                    st.warning("⚠️ API 키를 입력해주세요.")
                    st.session_state.dart = None
            except Exception as e:
                st.error(f"❌ 인증 실패: {str(e)}")
                st.session_state.dart = None
                st.session_state.api_key = None
        else:
            st.warning("⚠️ API 키를 입력해주세요.")
            st.session_state.dart = None
    
    st.markdown("---")
    
    # 인증 상태 표시
    if st.session_state.dart is not None:
        st.success("🟢 인증됨")
        
        # 재무제표 조회 기능
        st.header("📈 재무제표 조회")
        st.markdown("---")
        
        # 보고서 종류 선택
        report_type = st.selectbox(
            "보고서 종류",
            options=['1분기보고서', '반기보고서', '3분기보고서', '사업보고서'],
            help="조회할 보고서 종류를 선택하세요."
        )
        
        # 보고서 종류를 DART 코드로 변환
        report_code_map = {
            '1분기보고서': '11013',
            '반기보고서': '11012',
            '3분기보고서': '11014',
            '사업보고서': '11011'
        }
        
        # 분석 연도 선택 (multiselect)
        current_year = datetime.now().year
        available_years = list(range(2020, current_year + 1))
        default_years = [current_year - 2, current_year - 1, current_year] if current_year >= 2022 else [current_year]
        default_years = [y for y in default_years if y in available_years]
        
        selected_years = st.multiselect(
            "분석 연도 (다중 선택 가능)",
            options=available_years,
            default=default_years,
            help="분석할 연도를 여러 개 선택하세요. 기본값은 최근 3년입니다."
        )
        
        # 회사 선택 (1개만)
        st.markdown("### 기업 선택")
        
        # 자주 쓰는 줄임말 사전
        nickname_map = {
            '현대차': '현대자동차',
            '기아차': '기아',
            '하이닉스': 'SK하이닉스',
            '삼전': '삼성전자',
            '네이버': 'NAVER',
            '카카오뱅크': '카카오뱅크'
        }
        
        stock_name_input = st.text_input(
            "종목명",
            placeholder="예: 삼성전자",
            help="분석할 회사 1개를 입력하세요."
        )
        
        selected_company = None
        
        if stock_name_input:
            input_name = stock_name_input.strip()
            official_name = input_name
            
            # 별명 사전 확인
            if input_name in nickname_map:
                official_name = nickname_map[input_name]
                st.info(f"💡 '{input_name}' → '{official_name}'(으)로 변환하여 조회합니다.")
            else:
                # KRX 리스트에서 검색
                krx_data = get_stock_list_v3()
                if krx_data is not None:
                    if input_name in krx_data['Name'].values:
                        official_name = input_name
                    else:
                        candidates = krx_data[krx_data['Name'].str.contains(input_name, case=False, na=False)]
                        if not candidates.empty:
                            found_name = candidates.iloc[0]['Name']
                            official_name = found_name
                            st.info(f"🔍 '{input_name}' 검색 결과 중 '{found_name}'을(를) 선택했습니다.")
            
            selected_company = official_name
        
        # 데이터 가져오기 버튼
        st.markdown("---")
        if st.button("데이터 가져오기", type="primary", use_container_width=True):
            if selected_company and selected_years:
                try:
                    reprt_code = report_code_map[report_type]
                    all_dataframes = []
                    not_found_years = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    total_years = len(selected_years)
                    
                    # 연도별로 데이터 수집
                    for idx, year in enumerate(sorted(selected_years, reverse=True)):
                        status_text.text(f"조회 중: {selected_company} ({year}년) ({idx + 1}/{total_years})")
                        progress_bar.progress((idx + 1) / total_years)
                        
                        try:
                            corp_code = st.session_state.dart.find_corp_code(selected_company)
                            
                            if corp_code is None or corp_code == '':
                                not_found_years.append(f"{year}년(코드 미확인)")
                                continue
                            
                            data = st.session_state.dart.finstate(corp_code, year, reprt_code=reprt_code)
                            
                            if data is not None and not data.empty:
                                data.insert(0, '회사명', selected_company)
                                data.insert(1, '귀속년도', year)  # 귀속년도 컬럼 추가
                                all_dataframes.append(data)
                            else:
                                not_found_years.append(f"{year}년(데이터 없음)")
                                
                        except Exception as e:
                            not_found_years.append(f"{year}년(오류: {str(e)})")
                            continue
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if all_dataframes:
                        combined_data = pd.concat(all_dataframes, ignore_index=True)
                        
                        # 데이터 전처리: 금액 컬럼의 콤마 제거 및 숫자 변환
                        combined_data = preprocess_financial_data(combined_data)
                        
                        st.session_state.financial_data = combined_data
                        st.success(f"✅ {selected_company}의 {len(all_dataframes)}개 연도 데이터를 성공적으로 가져왔습니다!")
                        
                        if not_found_years:
                            st.warning(f"⚠️ 다음 연도는 데이터를 찾지 못했습니다: {', '.join(not_found_years)}")
                    else:
                        st.warning("⚠️ 조회된 데이터가 없습니다.")
                        st.session_state.financial_data = None
                        
                except Exception as e:
                    st.error(f"❌ 오류 발생: {str(e)}")
                    st.session_state.financial_data = None
            elif not selected_company:
                st.warning("⚠️ 조회할 기업을 입력해주세요.")
            elif not selected_years:
                st.warning("⚠️ 분석할 연도를 선택해주세요.")
    else:
        st.warning("🔴 미인증")

# ==========================================
# 🎯 메인 콘텐츠 영역
# ==========================================

st.title("📊 DART XBRL 기업 시계열 분석 리포트")
st.markdown("---")

if st.session_state.dart is None:
    st.info("👈 사이드바에서 DART API 키를 입력하고 인증해주세요.")
    st.markdown("""
    ### 사용 방법
    1. 사이드바에서 DART API 키를 입력합니다.
    2. '인증' 버튼을 클릭합니다.
    3. 인증이 완료되면 데이터 분석 기능을 사용할 수 있습니다.
    
    ### API 키 발급
    - [DART 공시시스템](https://opendart.fss.or.kr/)에서 회원가입 후 API 키를 발급받을 수 있습니다.
    """)
else:
    st.success("✅ DART API가 인증되었습니다. 데이터 분석을 시작할 수 있습니다.")
    
    # 재무제표 데이터가 있는 경우에만 탭 표시
    if 'financial_data' in st.session_state and st.session_state.financial_data is not None:
        financial_data = st.session_state.financial_data
        
        # 3개 탭 구성
        tab1, tab2, tab3 = st.tabs([
            "📋 Tab 1: 재무상태표 & 손익계산서 (Data)",
            "📊 Tab 2: 주요 재무비율 추이 (Ratios)",
            "📈 Tab 3: 시각화 (Trend Chart)"
        ])
        
        # ==========================================
        # Tab 1: 재무상태표 & 손익계산서 (피벗 형태)
        # ==========================================
        with tab1:
            st.header("📋 재무상태표 & 손익계산서")
            st.markdown("---")
            
            # 피벗 테이블 생성: 계정과목(행) x 귀속년도(열)
            if 'account_nm' in financial_data.columns and '귀속년도' in financial_data.columns and 'thstrm_amount' in financial_data.columns:
                # thstrm_amount가 숫자형인지 확인
                if not pd.api.types.is_numeric_dtype(financial_data['thstrm_amount']):
                    st.warning("⚠️ 금액 데이터가 숫자형이 아닙니다. 전처리를 다시 수행합니다.")
                    financial_data = preprocess_financial_data(financial_data)
                    st.session_state.financial_data = financial_data
                
                # 계정과목별, 연도별로 thstrm_amount를 피벗
                # aggfunc='sum'으로 설정하여 중복된 항목이 있으면 합치기
                pivot_df = financial_data.pivot_table(
                    index='account_nm',
                    columns='귀속년도',
                    values='thstrm_amount',
                    aggfunc='sum',  # 중복이 있을 경우 합계
                    fill_value=0  # 값이 없는 경우 0으로 채우기
                )
                
                # 연도 순서 정렬
                pivot_df = pivot_df.sort_index(axis=1)
                
                # 숫자 포맷팅 (억원 단위, 천 단위 콤마)
                pivot_df_formatted = pivot_df.copy()
                for col in pivot_df_formatted.columns:
                    pivot_df_formatted[col] = pivot_df_formatted[col].apply(
                        lambda x: f"{x:,.2f}" if pd.notna(x) and isinstance(x, (int, float)) and x != 0 else "-"
                    )
                
                st.dataframe(pivot_df_formatted, use_container_width=True, height=500)
                
                st.markdown("---")
                st.caption("💡 숫자는 억원 단위로 표시됩니다. 천 단위 콤마로 구분되어 있습니다.")
                
                # 원본 데이터도 제공 (접을 수 있게)
                with st.expander("📄 원본 데이터 보기"):
                    st.dataframe(financial_data, use_container_width=True, height=400)
            else:
                st.warning("⚠️ 피벗 테이블을 생성할 수 없습니다. 필요한 컬럼(account_nm, 귀속년도)이 없습니다.")
                st.dataframe(financial_data, use_container_width=True, height=400)
            
            # 엑셀 다운로드 버튼
            st.markdown("---")
            st.subheader("📥 데이터 다운로드")
            
            try:
                # 엑셀 파일로 변환
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    financial_data.to_excel(writer, index=False, sheet_name='재무제표')
                    if 'account_nm' in financial_data.columns and '귀속년도' in financial_data.columns:
                        pivot_df.to_excel(writer, sheet_name='피벗테이블')
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="📥 엑셀 파일로 다운로드 (.xlsx)",
                    data=excel_data,
                    file_name=f"재무제표_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
            except Exception as e:
                st.error(f"⚠️ 엑셀 다운로드 오류: {str(e)}")
                st.info("💡 openpyxl 패키지가 설치되어 있는지 확인해주세요: pip install openpyxl")
        
        # ==========================================
        # Tab 2: 주요 재무비율 추이 (연도별)
        # ==========================================
        with tab2:
            st.header("📊 주요 재무비율 추이")
            st.markdown("---")
            
            # 연도별 재무비율 계산
            ratios_df = calculate_financial_ratios_by_year(financial_data)
            
            if not ratios_df.empty:
                # 연도 순서 정렬
                ratios_df = ratios_df.sort_values(['회사명', '귀속년도'])
                
                # 수익성 지표
                st.subheader("💰 수익성 지표")
                profitability_cols = ['귀속년도', '영업이익률(%)', '순이익률(%)']
                profitability_df = ratios_df[['회사명'] + profitability_cols].copy()
                st.dataframe(profitability_df, use_container_width=True)
                
                st.markdown("---")
                
                # 안정성 지표
                st.subheader("🛡️ 안정성 지표")
                stability_cols = ['귀속년도', '부채비율(%)', '유동비율(%)']
                stability_df = ratios_df[['회사명'] + stability_cols].copy()
                st.dataframe(stability_df, use_container_width=True)
                
                st.markdown("---")
                
                # 성장성 지표
                st.subheader("📈 성장성 지표")
                growth_cols = ['귀속년도', '매출액증가율(%)']
                growth_df = ratios_df[['회사명'] + growth_cols].copy()
                st.dataframe(growth_df, use_container_width=True)
                
                st.markdown("---")
                
                # 전체 비율 요약
                st.subheader("📋 전체 재무비율 요약")
                st.dataframe(ratios_df, use_container_width=True)
                
                # 비율 해석 가이드
                with st.expander("💡 재무비율 해석 가이드"):
                    st.markdown("""
                    **수익성 지표:**
                    - **영업이익률**: 10% 이상이면 우수, 5% 이상이면 양호
                    - **순이익률**: 5% 이상이면 우수, 3% 이상이면 양호
                    
                    **안정성 지표:**
                    - **부채비율**: 100% 이하가 안정적, 200% 이상이면 위험
                    - **유동비율**: 100% 이상이면 단기 지급능력 양호
                    
                    **성장성 지표:**
                    - **매출액증가율**: 10% 이상이면 성장세, 음수면 감소
                    """)
            else:
                st.warning("⚠️ 재무비율을 계산할 수 없습니다. 재무제표 데이터 형식을 확인해주세요.")
                st.info("💡 필요한 계정명: 부채총계, 자본총계, 유동자산, 유동부채, 매출액, 영업이익, 당기순이익")
        
        # ==========================================
        # Tab 3: 시각화 (Trend Chart)
        # ==========================================
        with tab3:
            st.header("📈 재무제표 추이 시각화")
            st.markdown("---")
            
            # 차트 생성
            fig = create_trend_chart(financial_data)
            
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                st.info("💡 차트 위에 마우스를 올리면 정확한 수치를 확인할 수 있습니다.")
            else:
                st.warning("⚠️ 차트를 생성할 수 없습니다. 재무제표 데이터를 확인해주세요.")
                st.info("💡 매출액, 영업이익, 부채비율 데이터가 필요합니다.")
    else:
        st.info("👈 사이드바에서 기업을 입력하고 연도를 선택한 후 '데이터 가져오기' 버튼을 클릭하세요.")
