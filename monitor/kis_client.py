import json
import logging
import time
from datetime import datetime, timedelta

import pytz
import requests

import config

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


class KISClient:
    def __init__(self):
        self.base_url = config.KIS_BASE_URL
        self.app_key = config.KIS_APP_KEY
        self.app_secret = config.KIS_APP_SECRET
        self._access_token = None
        self._token_expires_at = 0

    def _load_cached_token(self):
        try:
            with open(config.TOKEN_CACHE_FILE, "r") as f:
                cache = json.load(f)
            if cache.get("expires_at", 0) > time.time():
                self._access_token = cache["access_token"]
                self._token_expires_at = cache["expires_at"]
                return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return False

    def _save_token_cache(self):
        cache = {"access_token": self._access_token, "expires_at": self._token_expires_at}
        with open(config.TOKEN_CACHE_FILE, "w") as f:
            json.dump(cache, f)

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        if self._load_cached_token():
            logger.info("캐시된 토큰 사용")
            return self._access_token
        url = f"{self.base_url}/oauth2/tokenP"
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + 23 * 3600
        self._save_token_cache()
        logger.info("새 토큰 발급 완료")
        return self._access_token

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": tr_id,
        }

    def get_current_price(self, stock_code: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        resp = requests.get(url, headers=self._headers("FHKST01010100"), params=params, timeout=10)
        resp.raise_for_status()
        o = resp.json().get("output", {})
        return {
            "price": int(o.get("stck_prpr", 0)),
            "change_pct": float(o.get("prdy_ctrt", 0)),
            "volume": int(o.get("acml_vol", 0)),
            "high": int(o.get("stck_hgpr", 0)),
            "low": int(o.get("stck_lwpr", 0)),
        }

    def place_sell_order(self, stock_code: str, quantity: int, price: int = 0) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        body = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "PDNO": stock_code, "ORD_DVSN": "01", "ORD_QTY": str(quantity), "ORD_UNPR": str(price),
        }
        resp = requests.post(url, headers=self._headers("TTTC0011U"), json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def place_buy_order(self, stock_code: str, quantity: int, price: int) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        body = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "PDNO": stock_code, "ORD_DVSN": "00", "ORD_QTY": str(quantity), "ORD_UNPR": str(price),
        }
        resp = requests.post(url, headers=self._headers("TTTC0802U"), json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers("TTTC8434R"), params=params, timeout=10)
        resp.raise_for_status()
        holdings = []
        for item in resp.json().get("output1", []):
            if int(item.get("hldg_qty", 0)) > 0:
                holdings.append({
                    "stock_code": item.get("pdno", ""), "name": item.get("prdt_name", ""),
                    "quantity": int(item.get("hldg_qty", 0)),
                    "avg_price": int(float(item.get("pchs_avg_pric", 0))),
                    "current_price": int(item.get("prpr", 0)),
                    "pnl_pct": float(item.get("evlu_pfls_rt", 0)),
                    "pnl_amt": int(item.get("evlu_pfls_amt", 0)),
                })
        return holdings

    def get_available_cash(self) -> int:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        params = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "PDNO": "005930", "ORD_UNPR": "0", "ORD_DVSN": "01",
            "CMA_EVLU_AMT_ICLD_YN": "Y", "OVRS_ICLD_YN": "Y",
        }
        resp = requests.get(url, headers=self._headers("TTTC8908R"), params=params, timeout=10)
        resp.raise_for_status()
        return int(resp.json().get("output", {}).get("ord_psbl_cash", 0))

    def cancel_order(
        self, krx_fwdg_ord_orgno: str, orgn_odno: str, quantity: int,
    ) -> dict:
        """미체결 주문 취소. TTTC0803U (실전)."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        body = {
            "CANO": config.KIS_CANO,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "KRX_FWDG_ORD_ORGNO": krx_fwdg_ord_orgno,
            "ORGN_ODNO": orgn_odno,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        resp = requests.post(url, headers=self._headers("TTTC0803U"), json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_pending_orders(self) -> list[dict]:
        """당일 미체결 매수 주문 조회. TTTC8001R + CCLD_DVSN=02."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        today = datetime.now(KST).strftime("%Y%m%d")
        params = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": today, "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "02",
            "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "02",
            "ORD_GNO_BRNO": "", "ODNO": "", "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers("TTTC8001R"), params=params, timeout=10)
        resp.raise_for_status()
        pending = []
        for item in resp.json().get("output1", []):
            rmn_qty = int(item.get("rmn_qty", 0))
            if rmn_qty > 0:
                pending.append({
                    "stock_code": item.get("pdno", ""),
                    "name": item.get("prdt_name", ""),
                    "order_qty": int(item.get("ord_qty", 0)),
                    "filled_qty": int(item.get("tot_ccld_qty", 0)),
                    "remaining_qty": rmn_qty,
                    "order_price": int(float(item.get("ord_unpr", 0))),
                    "odno": item.get("odno", ""),
                    "ord_gno_brno": item.get("ord_gno_brno", ""),
                })
        return pending

    def get_order_fills(self) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        today = datetime.now(KST).strftime("%Y%m%d")
        params = {
            "CANO": config.KIS_CANO, "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "02",
            "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "01", "ORD_GNO_BRNO": "",
            "ODNO": "", "INQR_DVSN_3": "00", "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers("TTTC8001R"), params=params, timeout=10)
        resp.raise_for_status()
        fills = []
        for item in resp.json().get("output1", []):
            qty = int(item.get("tot_ccld_qty", 0))
            if qty > 0:
                fills.append({
                    "stock_code": item.get("pdno", ""), "name": item.get("prdt_name", ""),
                    "quantity": qty, "price": int(float(item.get("avg_prvs", 0))),
                    "amount": int(item.get("tot_ccld_amt", 0)),
                })
        return fills

    def get_volume_ranking(self) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20101",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0", "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0", "FID_INPUT_DATE_1": "",
        }
        resp = requests.get(url, headers=self._headers("FHPST01710000"), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("output", []) or []

    def get_fluctuation_ranking(self, is_up: bool = True) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/ranking/fluctuation"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20170" if is_up else "20175",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0", "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0", "FID_INPUT_DATE_1": "",
        }
        resp = requests.get(url, headers=self._headers("FHPST01700000"), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("output", []) or []

    def get_daily_candles(self, stock_code: str) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        now = datetime.now(KST)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": (now - timedelta(days=365)).strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": now.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0",
        }
        resp = requests.get(url, headers=self._headers("FHKST03010100"), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("output2", []) or []

    def get_minute_candles(self, stock_code: str) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        now = datetime.now(KST)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": now.strftime("%H%M%S"), "FID_PW_DATA_INCU_YN": "Y",
        }
        resp = requests.get(url, headers=self._headers("FHKST03010200"), params=params, timeout=10)
        resp.raise_for_status()
        return (resp.json().get("output2", []) or [])[:12]

    def get_foreign_institution(self, stock_code: str) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        resp = requests.get(url, headers=self._headers("FHPTJ04400000"), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("output", []) or []

    def get_kospi_index(self) -> dict:
        return self._get_index("0001")

    def get_kosdaq_index(self) -> dict:
        return self._get_index("2001")

    def _get_index(self, iscd: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"
        params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd}
        resp = requests.get(url, headers=self._headers("FHPUP02100000"), params=params, timeout=10)
        resp.raise_for_status()
        o = resp.json().get("output", {})
        if not o:
            return {}
        return {
            "index_price": o.get("bstp_nmix_prpr", ""),
            "change_rate": o.get("bstp_nmix_prdy_ctrt", ""),
            "change_value": o.get("bstp_nmix_prdy_vrss", ""),
            "trading_value": o.get("acml_tr_pbmn", ""),
        }

    def get_exchange_rate(self) -> dict:
        try:
            resp = requests.get(
                "https://m.stock.naver.com/front-api/marketIndex/productDetail",
                params={"category": "exchange", "reutersCode": "FX_USDKRW"}, timeout=5,
            )
            resp.raise_for_status()
            r = resp.json().get("result", {})
            return {"exchange_rate": r.get("closePrice", ""), "change_rate": r.get("compareToPreviousClosePrice", "")}
        except Exception:
            return {}
