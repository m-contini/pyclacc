from typing import TypeAlias, Literal

FiscalYearType: TypeAlias = Literal[
    2009, 2010, 2011, 2012, 2013,
    2014, 2015, 2016, 2017, 2018,
    2019, 2020, 2021, 2022, 2023,
    2024, 2025, 2026, 2027, 2028,
    2029, 2030, 2031
]
ApproverCheckStatusType: TypeAlias = Literal[
    "All", "To check", "checked", "Under Investigation"
]
ClaccStatusType: TypeAlias = Literal[
    "All", "Approved", "Draft", "To Approve", "Approved 0", "Approved 1",
    "Approved 2", "Rejected", "Overwritten", "Overwritten Approved", "Proposal Refused"
]

WebCLACCParamsType: TypeAlias = tuple[FiscalYearType, ApproverCheckStatusType, ClaccStatusType]
