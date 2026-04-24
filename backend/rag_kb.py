
"""
rag_kb.py — AquaBot Knowledge Base for RAG Chatbot
===================================================
Contains curated domain knowledge chunks for irrigation science,
study region (Udham Singh Nagar), ISRO/IIRS, and crop data.

Used by the /api/chat endpoint for retrieval-augmented generation.
"""

import os
from typing import List, Dict, Optional
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE — Domain Chunks
# Each chunk: { "id", "tags", "text" }
# ─────────────────────────────────────────────────────────────────────────────

KNOWLEDGE_CHUNKS: List[Dict] = [

    {
        "id": "sys_overview",
        "tags": ["aquawatch", "system", "overview", "iirs", "isro", "irrigation", "monitoring"],
        "text": (
            "AquaWatch is a satellite-driven crop water monitoring system developed by ISRO/IIRS "
            "(Indian Institute of Remote Sensing, Dehradun) under the Department of Space, Government of India. "
            "It uses Sentinel-2 multispectral imagery to compute SAVI (Soil-Adjusted Vegetation Index), "
            "Kc (Crop Coefficient), CWR (Crop Water Requirement), and IWR (Irrigation Water Requirement) "
            "for Rabi wheat in Udham Singh Nagar, Uttarakhand. The system integrates SARIMAX time-series "
            "forecasting with FAO-56 physical models to provide 5, 10, and 15-day irrigation forecasts."
        )
    },
    {
        "id": "iirs_isro",
        "tags": ["iirs", "isro", "institute", "remote sensing", "dehradun", "department of space"],
        "text": (
            "IIRS — Indian Institute of Remote Sensing — is a premier institute under ISRO (Indian Space "
            "Research Organisation), Department of Space, Government of India, located in Dehradun, Uttarakhand. "
            "IIRS conducts research and training in remote sensing, GIS, and geospatial technologies. "
            "This irrigation monitoring project is developed as part of IIRS's applied remote sensing research "
            "for agricultural water management."
        )
    },
    {
        "id": "savi_def",
        "tags": ["savi", "vegetation index", "soil adjusted", "formula", "ndvi"],
        "text": (
            "SAVI — Soil-Adjusted Vegetation Index — is a vegetation index derived from Sentinel-2 satellite "
            "imagery. Formula: SAVI = ((NIR - Red) / (NIR + Red + L)) × (1 + L), where L = 0.5 is the "
            "soil correction factor. SAVI ranges from -1 to +1; healthy dense wheat crops typically show "
            "SAVI values of 0.4–0.8 during peak growth. It corrects NDVI for soil background effects, "
            "making it more accurate for sparse vegetation like early-stage wheat crops."
        )
    },
    {
        "id": "savi_kc_relation",
        "tags": ["savi", "kc", "crop coefficient", "relationship", "linear", "regression"],
        "text": (
            "In this system, the Crop Coefficient (Kc) is derived from SAVI using a linear regression "
            "equation established from field measurements and thesis research: Kc = 1.2088 × SAVI + 0.5375. "
            "This relationship (R² ≈ 0.89) converts the satellite-observed vegetation state into an agronomic "
            "coefficient used in water requirement calculations. Kc is bounded between 0.30 (bare soil) and "
            "1.15 (peak crop growth)."
        )
    },
    {
        "id": "kc_def",
        "tags": ["kc", "crop coefficient", "fao", "wheat", "growth stages"],
        "text": (
            "The Crop Coefficient (Kc) is a dimensionless factor that accounts for the difference between "
            "actual crop evapotranspiration and reference evapotranspiration (PET). For Rabi wheat: "
            "Kc_ini ≈ 0.30–0.40 (germination/emergence), Kc_mid ≈ 1.10–1.15 (heading/anthesis peak), "
            "Kc_end ≈ 0.35–0.45 (maturity/harvest). Kc varies with growth stage and is central to "
            "FAO-56 Penman-Monteith-based irrigation scheduling."
        )
    },
    {
        "id": "cwr_def",
        "tags": ["cwr", "crop water requirement", "formula", "pet", "evapotranspiration"],
        "text": (
            "CWR — Crop Water Requirement — is the total water consumed by the crop through "
            "evapotranspiration. Formula: CWR = Kc × PET, where PET is Potential Evapotranspiration "
            "(mm/day) and Kc is the Crop Coefficient. In this system, PET is forecast using a SARIMAX "
            "time-series model. CWR values for Rabi wheat in Udham Singh Nagar typically range from "
            "1.0–8.0 mm/day depending on growth stage and season. CWR represents the total demand; "
            "actual irrigation needed is IWR (net of rainfall)."
        )
    },
    {
        "id": "iwr_def",
        "tags": ["iwr", "irrigation water requirement", "rainfall", "effective rainfall", "peff"],
        "text": (
            "IWR — Irrigation Water Requirement — is the net amount of water that must be supplied by "
            "irrigation after accounting for effective rainfall. Formula: IWR = max(CWR − Peff, 0), where "
            "Peff is effective rainfall. In this system, effective rainfall is computed using USDA-SCS methods "
            "on 5-day accumulated rainfall totals. IWR values guide irrigation scheduling: when IWR > 20 mm/day, "
            "urgent irrigation is needed; IWR < 5 mm/day typically requires no irrigation. The system forecasts "
            "IWR for 5, 10, and 15-day windows to help farmers plan irrigation campaigns."
        )
    },
    {
        "id": "pet_def",
        "tags": ["pet", "potential evapotranspiration", "reference", "weather", "climate"],
        "text": (
            "PET — Potential Evapotranspiration — is the rate of water evaporated from soil and transpired from plants "
            "under non-limiting water conditions, measured in mm/day. It is driven by weather (temperature, humidity, "
            "wind, radiation) and estimated using the FAO-56 Penman-Monteith equation. In this system, PET is forecasted "
            "using a SARIMAX (Seasonal ARIMA with eXogenous variables) model trained on historical daily weather data. "
            "Typical PET values for Rabi wheat season in Uttarakhand range from 2–6 mm/day."
        )
    },
    {
        "id": "sarimax_forecast",
        "tags": ["sarimax", "forecast", "time series", "arima", "seasonal"],
        "text": (
            "SARIMAX (Seasonal AutoRegressive Integrated Moving Average with eXogenous variables) is a time-series "
            "forecasting model used to predict PET and Kc for 15 days ahead. The model accounts for: seasonal patterns "
            "(wheat phenology, temperature cycles), autoregressive structure (yesterday's PET influences today's), "
            "differencing (to remove trends), and moving averages (smoothing noise). SARIMAX order and exogenous variables "
            "(rainfall, day-of-year) are tuned on historical training data. The system re-trains models periodically as "
            "new data accumulates. Forecast accuracy (R² ≈ 0.75–0.85 on test data) is sufficient for irrigation planning."
        )
    },
    {
        "id": "wheat_phenology",
        "tags": ["wheat", "phenology", "growth stages", "rabi", "crop"],
        "text": (
            "Rabi wheat (winter wheat) in Uttarakhand follows a ~150-day cycle (November–April): "
            "(1) Sowing & Germination (Nov, 15 days): Kc ≈ 0.3–0.4, low water demand. "
            "(2) Vegetative Growth (Dec–Jan, 60 days): Kc ≈ 0.6–1.0, moderate demand, rapid LAI accumulation. "
            "(3) Heading & Anthesis (Feb, 20 days): Kc ≈ 1.10–1.15, peak water demand—critical for yield. "
            "(4) Grain Fill & Maturity (Mar–Apr, 40 days): Kc ≈ 0.8–0.4, declining demand. "
            "SAVI observations reflect these stages; Kc derived from SAVI tracks phenological progress without requiring "
            "ground truth."
        )
    },
    {
        "id": "study_region",
        "tags": ["study region", "udham singh nagar", "uttarakhand", "location", "climate"],
        "text": (
            "The study region is Udham Singh Nagar (formerly Nainital district), Uttarakhand, India. "
            "Coordinates: 29.0°N, 80.0°E. Elevation: 210–800 m ASL. Rabi wheat is grown on ~150,000 hectares. "
            "Climate: subtropical semi-arid; annual rainfall ≈ 1600 mm (80% in monsoon, June–Sept), leaving Rabi season "
            "(Nov–Apr) irrigation-dependent. Soil: alluvial, sandy loam, moderate water-holding capacity. "
            "Irrigation: farmer-managed tube wells and canal networks. The region typifies India's Indo-Gangetic breadbasket; "
            "results are applicable across similar zones (Punjab, Haryana, UP plains)."
        )
    },
    {
        "id": "sentinel2_data",
        "tags": ["sentinel 2", "satellite", "imagery", "multispectral", "data"],
        "text": (
            "Sentinel-2 is a polar-orbiting satellite constellation (A + B) operated by ESA, providing free, open-access "
            "multispectral imagery at 10 m resolution every 5 days at the equator. Key bands for SAVI: Red (B4, 650 nm) and "
            "Near-Infrared (B8, 842 nm). Sentinel-2 covers 290 km swath; Uttarakhand is imaged ~2–3 times per week "
            "(accounting for cloud cover). Processing chain: download Level-1C (TOA radiance), apply Sen2Cor atmospheric correction "
            "to produce Level-2A (surface reflectance), mask clouds, compute SAVI, reproject to local grid, archive in GeoServer."
        )
    },
    {
        "id": "fao56_standard",
        "tags": ["fao 56", "penman monteith", "irrigation", "standard", "methodology"],
        "text": (
            "FAO-56 (Crop Evapotranspiration – Guidelines for Computing Crop Water Requirements) is the international standard "
            "for irrigation water requirement estimation developed by the UN Food and Agriculture Organization. It defines: "
            "(1) Reference ET (ETₒ) using Penman-Monteith with standard weather variables. "
            "(2) Crop ET (ETc = Kc × ETₒ), where Kc is crop-stage specific. "
            "(3) Net irrigation requirement accounting for rainfall and soil water storage. "
            "This system implements FAO-56 Eq. 4: CWR = Kc × PET and Eq. 20: IWR = max(CWR − Peff, 0), ensuring "
            "recommendations are grounded in globally recognized agronomic science."
        )
    },
    {
        "id": "geoserver_deployment",
        "tags": ["geoserver", "deployment", "web service", "wms", "wcs"],
        "text": (
            "AquaWatch rasters (SAVI, Kc, CWR, IWR) are published via GeoServer, an open-source geospatial data server. "
            "GeoServer exposes layers via Web Map Service (WMS) for visualization and Web Coverage Service (WCS) for data download. "
            "The frontend (Vue.js/Leaflet) consumes WMS endpoints to display live maps; the API returns raster statistics and point queries. "
            "GeoServer also handles coordinate transformation, supporting both Web Mercator (for web maps) and the native "
            "UTM projection used internally."
        )
    },
    {
        "id": "irrigation_scheduling",
        "tags": ["irrigation scheduling", "water management", "farmer", "decision", "recommendations"],
        "text": (
            "Irrigation scheduling recommendations are based on IWR forecasts: "
            "• IWR < 5 mm/day: No irrigation needed. "
            "• IWR 5–15 mm/day: Light irrigation (1–2 cm) if soil moisture is depleted. "
            "• IWR 15–25 mm/day: Regular irrigation (2–3 cm) at standard intervals (7–10 days). "
            "• IWR > 25 mm/day: Urgent/heavy irrigation (4+ cm), especially during heading/anthesis. "
            "Farmers can use 5-day forecasts for weekly planning and 15-day forecasts for campaign planning (multiple events)."
        )
    },
    {
        "id": "satellite_limitations",
        "tags": ["limitations", "accuracy", "cloud", "uncertainty", "validation"],
        "text": (
            "Satellite-based monitoring has inherent limitations: (1) Cloud cover interrupts observations; during monsoon, "
            "cloud-free scenes are rare, introducing data gaps. (2) Pixel-level variability: 10 m Sentinel-2 pixels average "
            "across heterogeneous microplots; very small or irregularly-shaped fields are misrepresented. (3) Phenology variability: "
            "wheat ripens unevenly; SAVI from a uniform pixel may not reflect localized maturity. (4) Calibration drift: SAVI-to-Kc "
            "regression is fitted on one growing season; performance may degrade if cultivars or soil properties shift."
        )
    },
    {
        "id": "climate_change",
        "tags": ["climate change", "adaptation", "temperature", "rainfall", "future"],
        "text": (
            "Uttarakhand's climate is changing: temperatures are rising (~0.05°C/decade), monsoon onset is becoming erratic, "
            "and frost events are less predictable. These shifts alter: (1) PET (higher temperature → higher PET). "
            "(2) Crop phenology (warmer winters → earlier sowing, faster maturation). (3) Effective rainfall distribution "
            "(erratic monsoon → more irrigation variability). AquaWatch's SARIMAX models implicitly adapt to recent climate by "
            "training on recent data; but explicit trend detection and re-calibration are recommended annually."
        )
    },

]

# ─────────────────────────────────────────────────────────────────────────────
# LANGCHAIN RAG IMPLEMENTATION
# ─────────────────────────────────────────────────────────────────────────────

class LangChainRAG:
    """
    Manages the LangChain RAG pipeline: Embeddings, Vector Store, and QA Chain.
    """
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for LangChainRAG")
            
        self.api_key = api_key
        
        # 1. Initialize Embeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            google_api_key=api_key
        )
        
        # 2. Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
            google_api_key=api_key,
            temperature=0.2
        )
        
        # 3. Create Vector Store from KNOWLEDGE_CHUNKS
        documents = [
            Document(
                page_content=chunk["text"],
                metadata={"id": chunk["id"], "tags": ",".join(chunk["tags"])}
            )
            for chunk in KNOWLEDGE_CHUNKS
        ]
        
        self.vector_store = FAISS.from_documents(documents, self.embeddings)
        
    def _build_prompt(
        self,
        query: str,
        docs: List[Document],
        live_data: Optional[Dict] = None,
        history: Optional[List[Dict]] = None,
    ) -> str:
        context_parts = []

        if docs:
            context_parts.append("[KNOWLEDGE BASE]")
            for doc in docs:
                chunk_id = doc.metadata.get("id", "unknown")
                context_parts.append(f"- ({chunk_id}) {doc.page_content}")

        if live_data:
            context_parts.append("\n[LIVE SYSTEM DATA]")
            for key, value in live_data.items():
                context_parts.append(f"- {key.upper()}: {value}")

        if history:
            context_parts.append("\n[RECENT CHAT HISTORY]")
            for item in history[-6:]:
                role = str(item.get("role", "user")).upper()
                content = str(item.get("content", "")).strip()
                if content:
                    context_parts.append(f"- {role}: {content}")

        context = "\n".join(context_parts).strip() or "No additional context available."

        return f"""
You are AquaBot, an expert irrigation and crop water management assistant
for the AquaWatch system developed by ISRO/IIRS for Rabi wheat in
Udham Singh Nagar, Uttarakhand, India.

Instructions:
- Answer accurately using the provided context.
- The user may ask in English or Hinglish.
- Use a helpful, professional tone.
- Use light markdown when it helps readability.
- If live data is present, use it in the answer.
- If the answer is not supported by the context, say you do not know.

CONTEXT:
{context}

USER QUESTION:
{query}

ANSWER:
""".strip()

    def get_response(
        self,
        query: str,
        live_data: Optional[Dict] = None,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Generate a response using the LangChain RAG pipeline.
        """
        docs = self.vector_store.similarity_search(query, k=5)
        prompt = self._build_prompt(query, docs, live_data=live_data, history=history)
        result = self.llm.invoke(prompt)
        answer = getattr(result, "content", result)
        if isinstance(answer, list):
            answer = "\n".join(str(part) for part in answer)

        return {
            "answer": str(answer).strip(),
            "sources": [doc.metadata["id"] for doc in docs]
        }

    def retrieve_raw(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Simple retrieval of relevant chunks.
        """
        docs = self.vector_store.similarity_search(query, k=top_k)
        return [
            {"id": d.metadata["id"], "text": d.page_content, "tags": d.metadata["tags"].split(",")} 
            for d in docs
        ]

# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON INSTANCE
# ─────────────────────────────────────────────────────────────────────────────

_RAG_INSTANCE: Optional[LangChainRAG] = None

def get_rag_system() -> LangChainRAG:
    global _RAG_INSTANCE
    if _RAG_INSTANCE is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")
        _RAG_INSTANCE = LangChainRAG(api_key)
    return _RAG_INSTANCE

# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD COMPATIBLE WRAPPERS (for main.py)
# ─────────────────────────────────────────────────────────────────────────────

def retrieve(query: str, top_k: int = 5) -> List[Dict]:
    """Retrieve relevant chunks using FAISS."""
    try:
        return get_rag_system().retrieve_raw(query, top_k)
    except Exception:
        return []

def build_context(query: str, live_data: Optional[Dict] = None, top_k: int = 3) -> str:
    """Build context string from retrieved chunks and live data."""
    chunks = retrieve(query, top_k=top_k)
    context_parts = ["[KNOWLEDGE BASE]"]
    for c in chunks:
        context_parts.append(f"• {c['text']}")
    
    if live_data:
        context_parts.append("\n[LIVE SYSTEM DATA]")
        for k, v in live_data.items():
            context_parts.append(f"• {k.upper()}: {v}")
            
    return "\n".join(context_parts)

def get_chat_answer(
    query: str,
    live_data: Optional[Dict] = None,
    history: Optional[List[Dict]] = None,
) -> Dict:
    """Main entry point for main.py to get a RAG response."""
    try:
        return get_rag_system().get_response(query, live_data=live_data, history=history)
    except Exception as e:
        print(f"LangChain RAG failed: {e}")
        return {"answer": fallback_answer(query), "sources": []}

def fallback_answer(query: str) -> str:
    """Basic rule-based fallback if LLM is unavailable."""
    query_lower = query.lower()
    if "savi" in query_lower:
        return "SAVI stands for Soil-Adjusted Vegetation Index. It's used to monitor crop health while correcting for soil background."
    if "kc" in query_lower:
        return "Kc is the Crop Coefficient, which helps estimate water needs based on growth stage."
    return "I'm currently having trouble connecting to my brain. Please try again later, or ask about SAVI, Kc, or IWR."

if __name__ == "__main__":
    test_query = "What is SAVI?"
    print(f"\nQuery: {test_query}")
    ans = get_chat_answer(test_query)
    print(f"Answer: {ans['answer']}")
    print(f"Sources: {ans['sources']}")
