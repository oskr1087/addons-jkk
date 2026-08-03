/** @odoo-module **/

// ==========================================================================
// Copyright © 2026 TugIT. All rights reserved.
// ==========================================================================

var zpl;

export class ZPLModal {

    bindModalIcon() {
        document.getElementById('zplReportModalCloseIco').addEventListener('click', this._closeZPLViewerModal.bind(this));
        document.getElementById('zplReportModalCloseBtn').addEventListener('click', this._closeZPLViewerModal.bind(this));
        document.getElementById('QZConnectionBtnR').addEventListener('click', this._connectQZ.bind(this));
        document.getElementById('QZListPrinterBtnR').addEventListener('click', this._listQZPrinter.bind(this));
        document.getElementById('zplViewerModalPrintBtnR').addEventListener('click', this._printZPLraw.bind(this));
        document.getElementById('zplReportDownload').addEventListener('click', this._downloadZPLfile.bind(this));
    }

    // QZ
    async _connectQZ(ev) {
        ev.stopImmediatePropagation();
        try {
            let conn = await odoo.qz.connect();
            if (conn.conn) {
                this.showIcon();
            } else {
                this.hideIcon();
            }
            const zplPrinter = localStorage.getItem('ZPL-printer');
            if (zplPrinter) {
                const el = document.getElementById("QZPrinterListAreaR");
                el.options.length = 0;
                let option = document.createElement("option");
                option.value = zplPrinter;
                option.textContent = zplPrinter;
                el.appendChild(option);
            };
        } catch (err) {
            console.error("Cannot connect to QZ:", err);
            this.hideIcon();
        }
    }

    async _listQZPrinter(ev) {
        ev.stopImmediatePropagation();
        try {

            let res = await odoo.qz.listPrinters("QZPrinterListAreaR");
            if (res.conn) {
                const el = document.getElementById("QZPrinterListAreaR");
                el.options.length = 0;
                document.getElementById("QZPrinterLabelAreaR").style.color = ""
                res.printers.forEach(name => {
                    let option = document.createElement("option");
                    option.value = name;
                    option.textContent = name;
                    el.appendChild(option);
                });
            } else {
                this.hideIcon();
            }
        } catch (err) {
            this.hideIcon();
        }
    }

    async _printZPLraw(ev) {
        ev.stopImmediatePropagation()
        const printer = document.getElementById("QZPrinterListAreaR").value
        if (printer === '') {
            document.getElementById("QZPrinterLabelAreaR").style.color = "red";
            document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-times-circle text-warning" aria-hidden="true"></i> Please select a printer.'
            document.getElementById("zplReport_loading").style.display = "block";
            setTimeout(() => {
                document.getElementById("zplReport_loading").style.display = "none";
            }, 3000);
        } else {
            localStorage.setItem('ZPL-printer', printer);
            document.getElementById("QZPrinterLabelAreaR").style.color = "green"
            try {
                // Mostrar estado de enviando
                document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-spinner fa-spin text-info" aria-hidden="true"></i> Sending labels to ' + printer + '...'
                document.getElementById("zplReport_loading").style.display = "block";

                let res = await odoo.qz.printRaw(printer, zpl)

                if (res.conn) {
                    // Mostrar mensaje de éxito con cantidad de etiquetas
                    document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-check-circle text-success" aria-hidden="true"></i> ' + res.message
                    document.getElementById("zplReport_loading").style.display = "block";
                    setTimeout(() => {
                        document.getElementById("zplReport_loading").style.display = "none";
                    }, 4000);
                } else {
                    // Mostrar error
                    document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-times-circle text-danger" aria-hidden="true"></i> Error: ' + res.message
                    document.getElementById("zplReport_loading").style.display = "block";
                    setTimeout(() => {
                        document.getElementById("zplReport_loading").style.display = "none";
                    }, 4000);
                    this.hideIcon();
                }
            } catch (err) {
                console.error("[v0] Print error:", err);
                document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-times-circle text-danger" aria-hidden="true"></i> Print error: ' + err.message
                document.getElementById("zplReport_loading").style.display = "block";
                setTimeout(() => {
                    document.getElementById("zplReport_loading").style.display = "none";
                }, 4000);
                this.hideIcon();
            }
        }
    }

    // Set icon visibility
    showIcon() {
        document.getElementById("QZConnectionBtnR").style.color = "green";
        document.getElementById("QZListPrinterBtnR").style.display = "inline";
        document.getElementById("zplViewerModalPrintBtnR").style.display = "inline";
        document.getElementById("QZPrinterAreaR").classList.remove("d-none");
    }
    hideIcon() {
        document.getElementById("QZConnectionBtnR").style.color = "red";
        document.getElementById("QZConnectionBtnR").title = "Click to Reconnect.\nCheck if QZ Tray is running or not.";
        document.getElementById("QZListPrinterBtnR").style.display = "none";
        document.getElementById("zplViewerModalPrintBtnR").style.display = "none";
        document.getElementById("QZPrinterAreaR").classList.add("d-none");
        document.getElementById("zplReport_loading").innerHTML = '<i class="fa fa-times-circle text-danger" aria-hidden="true"></i> Disconnected from QZ Tray!'
        document.getElementById("zplReport_loading").style.display = "block";
        setTimeout(() => {
            document.getElementById("zplReport_loading").style.display = "none";
        }, 3000);
    }

    zplViewerConfig() {
        let value = localStorage.getItem(key);
        if (value === null) {
            localStorage.setItem(key, defaultValue);
            value = defaultValue;
        }
        return value;
    }

    _downloadZPLfile() {
        const blob = new Blob([zpl], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const now = new Date();
        const timestamp = now.getFullYear()
            + "-" + String(now.getMonth() + 1).padStart(2, "0")
            + "-" + String(now.getDate()).padStart(2, "0")
            + "_" + String(now.getHours()).padStart(2, "0")
            + "-" + String(now.getMinutes()).padStart(2, "0")
            + "-" + String(now.getSeconds()).padStart(2, "0");
        a.download = "label" + timestamp + ".zpl";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    _closeZPLViewerModal() {
        const modalElement = document.getElementById('zplReportModal');
        if (modalElement) {
            if (document.activeElement) {
                document.activeElement.blur(); // Remove focus from whatever is currently focused
            }
            modalElement.style.display = "none";
            modalElement.classList.remove("show");
            modalElement.setAttribute("aria-hidden", "true");
            const closeIcon = document.getElementById('zplReportModalCloseIco');
            if (closeIcon) {
                closeIcon.style.display = 'none';
            }
        }
    }

    // Show modal and load zpl label in view
    async zplReportHandler(zpldata) {
        zpl = zpldata
        this.bindModalIcon()
        const modalElement = document.getElementById('zplReportModal');
        modalElement.style.display = 'block';
        modalElement.classList.add('show');
        modalElement.removeAttribute("aria-hidden");
        document.getElementById('zplReportModalCloseIco').style.display = 'inline';
    }
}
