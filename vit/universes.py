"""Liste predefinite di titoli da analizzare (ticker Yahoo Finance)."""

UNIVERSES = {
    "usa_quality": {
        "name": "USA – grandi aziende di qualità",
        "tickers": [
            "AAPL", "MSFT", "GOOGL", "META", "AMZN", "BRK-B", "JNJ", "PG", "KO", "PEP", "V", "MA", "UNH", "HD",
            "MCD", "COST", "WMT", "NKE", "SBUX", "ADP", "ACN", "TXN", "ORCL", "CSCO", "QCOM", "ADBE", "LOW",
            "CAT", "DE", "HON", "UPS", "LMT", "ABBV", "MRK", "PFE", "AMGN", "GILD", "MO", "PM", "CL", "KMB",
            "GIS", "HSY", "TGT", "AZO", "ORLY", "MCO", "SPGI", "MSCI", "CTAS", "FAST", "VRSK", "AXP", "JPM",
            "BAC", "OXY", "CVX", "KR", "DPZ", "ROL",
        ],
    },
    "ftse_mib": {
        "name": "Italia – FTSE MIB",
        "tickers": [
            "ENI.MI", "ENEL.MI", "ISP.MI", "UCG.MI", "STLAM.MI", "RACE.MI", "G.MI", "MONC.MI", "PRY.MI",
            "LDO.MI", "TRN.MI", "SRG.MI", "PST.MI", "CPR.MI", "REC.MI", "DIA.MI", "AMP.MI", "TEN.MI",
            "HER.MI", "A2A.MI", "INW.MI", "IP.MI", "BC.MI", "BMED.MI", "BAMI.MI", "BPE.MI", "FBK.MI",
            "NEXI.MI", "PIRC.MI", "TIT.MI", "UNI.MI", "AZM.MI", "IG.MI", "IVG.MI", "BMPS.MI", "MB.MI",
        ],
    },
    "europe_quality": {
        "name": "Europa – campioni di qualità",
        "tickers": [
            "NESN.SW", "RO.SW", "NOVN.SW", "MC.PA", "OR.PA", "RMS.PA", "ASML.AS", "SAP.DE", "NOVO-B.CO",
            "ULVR.L", "DGE.L", "AI.PA", "SU.PA", "EL.PA", "ITX.MC", "ADS.DE", "SIE.DE", "ALV.DE", "MUV2.DE",
            "AZN.L", "GSK.L", "REL.L", "BATS.L", "HEIA.AS", "WKL.AS", "ABI.BR", "DSY.PA", "ATCO-A.ST",
            "RACE.MI", "LISN.SW",
        ],
    },
}
