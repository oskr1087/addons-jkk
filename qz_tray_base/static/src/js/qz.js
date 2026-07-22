// ==========================================================================
// Copyright © 2026 TugIT. All rights reserved.
// QZ TRAY JAVASCRIPT FOR ODOO
// ==========================================================================

window.odoo = window.odoo || {};
odoo.qz = {

    // -------------------------------------------------------------
    // 1. CERTIFICATE & SIGNATURE (DEV MODE — UNSIGNED)
    // -------------------------------------------------------------
    initSecurity() {
        qz.security.setCertificatePromise((resolve, reject) => {
            resolve({
                promise: (res) => res("UNSIGNED")    // Development only
            });
        });

        qz.security.setSignaturePromise((toSign) => {
            return (resolve, reject) => resolve("test-signature"); // Dev only
        });
    },

    // -------------------------------------------------------------
    // 2. CONNECT TO QZ TRAY
    // -------------------------------------------------------------
    async connect() {
        if (qz.websocket.isActive()) {
            // return Promise.resolve();
            return {"conn": true, "message":"Already connected."}
        }
        return qz.websocket.connect()
            .then(() => {
                return {"conn": true, "message":"Connected."}
            })
            .catch(err => {
                return {"conn": false, "message":"Disconnected."}
            });
    },

    // async connect() {
    //     const info = await qz.websocket.getConnectionInfo();
    //     if (info.state === "OPEN") {
    //         console.log("Already connected");
    //         return { conn: true, message: "Already connected." };
    //     }
    //     try {
    //         await qz.websocket.connect();
    //         console.log("Connected");
    //         return { conn: true, message: "Connected." };
    //     } catch (err) {
    //         console.log("Disconnected", err);
    //         return { conn: false, message: "Disconnected." };
    //     }
    // },

    // -------------------------------------------------------------
    // 3. LIST PRINTERS
    // -------------------------------------------------------------
    listPrinters() {
        return qz.printers.find()
            .then(printers => {
                return {"conn": true, "printers": printers}
            })
            .catch(err => {
                return {"conn": false, "message":"Disconnected"}
            });
    },


    // -------------------------------------------------------------
    // 4. PRINT RAW TEXT (ESCPOS / ZPL)
    // -------------------------------------------------------------
    printRaw(printerName, text) {
        if(qz.websocket.isActive()){
            const config = qz.configs.create(printerName);
            const data = [
                { type: "raw", format: "plain", data: text }
            ];
            return qz.print(config, data)
            .then(() => {
                return {"conn": true, "message":"Sent to printer."}
            })
            .catch(err => {
                console.log('QZ Tray: Raw print error:', err)
                return {"conn": false, "message":"Error on print Raw."}
            });
        }else{
            return {"conn": false, "message":"Disconnected."}
        }
    },

    // -------------------------------------------------------------
    // 5. PRINT PDF
    // -------------------------------------------------------------
    printPDF(pdfUrl, printerName = null) {
        if(qz.websocket.isActive()){
            const config = qz.configs.create(printerName);
            const data = [
                { type: "pdf", data: pdfUrl }
            ];
            return qz.print(config, data)
            .then(() => {
                return {"conn": true, "message":"Sent to printer."}
            })
            .catch(err => {
                console.error("QZ Tray: PDF print error:", err)
                return {"conn": false, "message":"Error on print PDF."}
            });
        }else{
            return {"conn": false, "message":"Disconnected."}
        }
    }

};


// ==========================================================================
// AUTO-INITIALIZE SECURITY ON PAGE LOAD
// ==========================================================================
document.addEventListener("DOMContentLoaded", function () {
    if (window.qz) {
        odoo.qz.initSecurity();
    } else {
        console.error("QZ Tray library not loaded!");
    }
});



