"""
generate_sample_pdf.py — Creates a synthetic AUTOSAR HLD PDF for testing and demo.

Run this script once to produce demo/sample_docs/sample_hld.pdf.
The document uses realistic AUTOSAR terminology without being a real proprietary file.

Usage:
    python demo/generate_sample_pdf.py
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

OUTPUT_PATH = Path(__file__).parent / "sample_docs" / "sample_hld.pdf"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def build_pdf():
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    h1  = styles["Heading1"]
    h2  = styles["Heading2"]
    h3  = styles["Heading3"]
    body = styles["BodyText"]
    body.spaceAfter = 6

    story = []

    # ── Cover page ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Battery Management System", h1))
    story.append(Paragraph("AUTOSAR High-Level Design Document", h2))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("Document Version: 2.3", body))
    story.append(Paragraph("Classification: Internal Engineering Use Only", body))
    story.append(PageBreak())

    # ── Page 2: Table of Contents ─────────────────────────────────────────────
    story.append(Paragraph("Table of Contents", h1))
    toc_items = [
        "1. System Overview",
        "2. Software Component Descriptions",
        "   2.1 BatteryManagement SWC",
        "   2.2 ThermalManagement SWC",
        "   2.3 PowerControl SWC",
        "3. Port and Interface Definitions",
        "4. Signal List",
        "5. Integration Notes",
    ]
    for item in toc_items:
        story.append(Paragraph(item, body))
    story.append(PageBreak())

    # ── Page 3: System Overview ────────────────────────────────────────────────
    story.append(Paragraph("1. System Overview", h1))
    story.append(Paragraph(
        "This document describes the High-Level Design (HLD) of the Battery Management "
        "System (BMS) implemented using AUTOSAR methodology. The system is composed of "
        "three primary Software Components (SWCs): BatteryManagement, ThermalManagement, "
        "and PowerControl. Each SWC is an AtomicSWC running on the AUTOSAR Runtime "
        "Environment (RTE). Communication between SWCs is mediated through the RTE using "
        "defined PortInterfaces.", body))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "The BMS ECU runs on a 32-bit microcontroller. The BSW (Basic Software) layer "
        "provides services including OS scheduling, NvM, COM, and diagnostic modules. "
        "SWC communication follows the Sender-Receiver (S/R) and Client-Server (C/S) "
        "paradigms as defined in the AUTOSAR standard.", body))
    story.append(PageBreak())

    # ── Page 4: BatteryManagement SWC ─────────────────────────────────────────
    story.append(Paragraph("2. Software Component Descriptions", h1))
    story.append(Paragraph("2.1 BatteryManagement SWC", h2))
    story.append(Paragraph(
        "The BatteryManagement SWC is responsible for monitoring cell voltages, state of "
        "charge estimation, and fault detection. It is an AtomicSWC with one InternalBehavior "
        "containing three Runnables: Runnable_BattInit (initialisation), "
        "Runnable_BattMonitor (10 ms cyclic), and Runnable_BattFault (event-triggered).", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Ports:", h3))

    batt_ports = [
        ["Port Name", "Direction", "Interface", "Description"],
        ["BattVoltage_Prov", "P-Port", "BattVoltage_If", "Provides cell voltage data"],
        ["BattSOC_Prov",     "P-Port", "BattSOC_If",     "Provides state-of-charge"],
        ["BattTemp_Req",     "R-Port", "TempSensor_If",   "Requires temperature reading"],
        ["BattFault_Prov",   "P-Port", "FaultStatus_If",  "Provides fault status flag"],
    ]
    t = Table(batt_ports, colWidths=[4 * cm, 2.5 * cm, 4 * cm, 5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ── Page 5: ThermalManagement SWC ─────────────────────────────────────────
    story.append(Paragraph("2.2 ThermalManagement SWC", h2))
    story.append(Paragraph(
        "The ThermalManagement SWC reads temperature sensors and provides thermal data "
        "to other SWCs. It also controls cooling fan output based on temperature thresholds. "
        "It is an AtomicSWC with one Runnable: Runnable_ThermalCycle (20 ms cyclic).", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Ports:", h3))

    thermal_ports = [
        ["Port Name", "Direction", "Interface", "Description"],
        ["TempSensor_Prov",   "P-Port", "TempSensor_If",    "Provides temperature readings"],
        ["CoolingCmd_Prov",   "P-Port", "CoolingCmd_If",    "Provides cooling fan command"],
        ["BattFault_Req",     "R-Port", "FaultStatus_If",   "Requires battery fault flag"],
    ]
    t2 = Table(thermal_ports, colWidths=[4 * cm, 2.5 * cm, 4 * cm, 5 * cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t2)
    story.append(PageBreak())

    # ── Page 6: PowerControl SWC ───────────────────────────────────────────────
    story.append(Paragraph("2.3 PowerControl SWC", h2))
    story.append(Paragraph(
        "The PowerControl SWC manages the main contactor relay and power distribution "
        "logic. It decides when to enable or disable battery output based on state of "
        "charge, fault conditions, and thermal status. It is an AtomicSWC with Runnables: "
        "Runnable_PowerInit and Runnable_PowerControl (5 ms cyclic).", body))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Ports:", h3))

    power_ports = [
        ["Port Name", "Direction", "Interface", "Description"],
        ["BattSOC_Req",      "R-Port", "BattSOC_If",     "Requires state-of-charge"],
        ["BattVoltage_Req",  "R-Port", "BattVoltage_If", "Requires cell voltage data"],
        ["CoolingCmd_Req",   "R-Port", "CoolingCmd_If",  "Requires cooling fan command"],
        ["RelayCmd_Prov",    "P-Port", "RelayCmd_If",    "Provides relay enable/disable"],
        # Intentional error: BattFault is referenced here as P-Port but is P-Port in BatteryManagement too
        ["BattFault_Prov",   "P-Port", "FaultStatus_If", "Note: should be R-Port (intentional inconsistency)"],
    ]
    t3 = Table(power_ports, colWidths=[4 * cm, 2.5 * cm, 4 * cm, 5 * cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t3)
    story.append(PageBreak())

    # ── Page 7: Interface Definitions ─────────────────────────────────────────
    story.append(Paragraph("3. Port and Interface Definitions", h1))
    story.append(Paragraph(
        "All PortInterfaces used in this system follow the AUTOSAR SenderReceiver or "
        "ClientServer paradigm. The table below lists all defined interfaces.", body))
    story.append(Spacer(1, 0.3 * cm))

    interfaces = [
        ["Interface Name",  "Type",           "DataElements / Operations", "Units"],
        ["BattVoltage_If",  "SenderReceiver",  "CellVoltage_Val",           "mV"],
        ["BattSOC_If",      "SenderReceiver",  "SOC_Val",                   "%"],
        ["TempSensor_If",   "SenderReceiver",  "Temperature_Val",           "°C"],
        ["FaultStatus_If",  "SenderReceiver",  "FaultActive_Bool",          "boolean"],
        ["CoolingCmd_If",   "SenderReceiver",  "FanDutyCycle_Val",          "%"],
        ["RelayCmd_If",     "SenderReceiver",  "RelayEnable_Bool",          "boolean"],
        # Intentional omission: BattFault_If is referenced in Port table but not defined here
    ]
    t4 = Table(interfaces, colWidths=[4 * cm, 3.5 * cm, 5 * cm, 3 * cm])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t4)
    story.append(PageBreak())

    # ── Page 8: Signal List ────────────────────────────────────────────────────
    story.append(Paragraph("4. Signal List", h1))
    story.append(Paragraph(
        "The following signals are exchanged between SWCs via the AUTOSAR RTE. "
        "All signals are transmitted using the implicit S/R communication mechanism "
        "unless stated otherwise.", body))
    story.append(Spacer(1, 0.3 * cm))

    signals = [
        ["Signal Name",          "Producer SWC",       "Consumer SWC",  "Update Rate"],
        ["CellVoltage_Sig",      "BatteryManagement",  "PowerControl",   "10 ms"],
        ["SOC_Sig",              "BatteryManagement",  "PowerControl",   "10 ms"],
        ["Temperature_Sig",      "ThermalManagement",  "BatteryManagement", "20 ms"],
        ["FaultActive_Sig",      "BatteryManagement",  "ThermalManagement", "Event"],
        ["FanDutyCycle_Sig",     "ThermalManagement",  "PowerControl",   "20 ms"],
        ["RelayEnable_Sig",      "PowerControl",       "BSW_IoHwAb",     "5 ms"],
        # Intentional: OrphanSignal_Sig is defined here but has no consumer
        ["OrphanSignal_Sig",     "BatteryManagement",  "—",              "100 ms"],
    ]
    t5 = Table(signals, colWidths=[4.5 * cm, 4 * cm, 4 * cm, 3 * cm])
    t5.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t5)
    story.append(PageBreak())

    # ── Page 9: Integration Notes ──────────────────────────────────────────────
    story.append(Paragraph("5. Integration Notes", h1))
    story.append(Paragraph(
        "The following notes apply during software integration on the target ECU:", body))
    story.append(Spacer(1, 0.3 * cm))
    notes = [
        "The BatteryManagement SWC must be initialised before the PowerControl SWC. "
        "Ensure Runnable_BattInit completes before the first invocation of Runnable_PowerControl.",
        "The ThermalManagement SWC reads temperature via a hardware abstraction layer (IoHwAb). "
        "Ensure the IoHwAb SWC is mapped to the correct ADC channel for the temperature sensor.",
        "The RTE generation tool must be configured with the correct task mapping for all cyclic runnables. "
        "Runnable_BattMonitor (10 ms) and Runnable_PowerControl (5 ms) share OS Task T2.",
        "The FaultStatus_If interface must be configured with InitValue = FALSE in the AUTOSAR configuration tool. "
        "Failure to set this may result in a spurious fault at startup.",
        "Signal OrphanSignal_Sig is defined in the signal list but currently has no consumer SWC assigned. "
        "This should be resolved before final integration.",
    ]
    for n in notes:
        story.append(Paragraph(f"• {n}", body))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    print(f"Sample HLD PDF generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
