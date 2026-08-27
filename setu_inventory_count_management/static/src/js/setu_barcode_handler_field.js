/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import * as BarcodeScanner from "@web/core/barcode/barcode_dialog";
import { charField, CharField } from "@web/views/fields/char/char_field";
import { _t } from "@web/core/l10n/translation";
import mobile from "@web_mobile/js/services/core";

/**
 * Escáner de inventario compatible con:
 * - App móvil nativa de Odoo: usa primero el bridge nativo web_mobile.
 * - Navegador / PWA: usa el lector web estándar de Odoo.
 * - PDA / USB / Bluetooth: mantiene el bus estándar barcode_scanned.
 *
 * En la app móvil NO usamos primero getUserMedia(), porque la cámara debe
 * solicitarse mediante el bridge nativo de Odoo (scanBarcode).
 */
export class SetuBarcodeHandlerField extends CharField {
    static props = {
        ...CharField.props,
        canScanBarcode: { type: Boolean, optional: true },
    };

    setup() {
        super.setup();
        this.barcodeService = useService("barcode");
        this.notification = useService("notification");
    }

    _normalizeBarcode(scannedValue) {
        if (!scannedValue) {
            return false;
        }
        if (typeof scannedValue === "string") {
            return scannedValue.trim();
        }
        // Compatibilidad defensiva entre versiones del bridge móvil.
        const value =
            scannedValue.code ||
            scannedValue.barcode ||
            scannedValue.data ||
            scannedValue.value;
        return typeof value === "string" ? value.trim() : value || false;
    }

    _hasNativeScanner() {
        return Boolean(
            mobile &&
            mobile.methods &&
            typeof mobile.methods.scanBarcode === "function"
        );
    }

    async _scanWithNativeApp() {
        const result = await mobile.methods.scanBarcode();
        return this._normalizeBarcode(result);
    }

    async _scanWithWebCamera() {
        const result = await BarcodeScanner.scanBarcode(this.env);
        return this._normalizeBarcode(result);
    }

    _emitBarcode(barcode) {
        // Mismo evento que usa un lector USB/Bluetooth/PDA.
        this.barcodeService.bus.trigger("barcode_scanned", { barcode });
    }

    _successFeedback() {
        // En app Odoo preferimos vibración nativa.
        if (
            mobile &&
            mobile.methods &&
            typeof mobile.methods.vibrate === "function"
        ) {
            try {
                mobile.methods.vibrate({ duration: 100 });
                return;
            } catch {
                // Si el bridge no responde, usamos la API web si existe.
            }
        }
        if (window.navigator && "vibrate" in window.navigator) {
            window.navigator.vibrate(100);
        }
    }

    async openMobileScanner() {
        let barcode = false;
        try {
            if (this._hasNativeScanner()) {
                // App móvil Odoo: cámara nativa mediante web_mobile.
                barcode = await this._scanWithNativeApp();
            } else {
                // Safari/Chrome/PWA: lector web estándar.
                barcode = await this._scanWithWebCamera();
            }

            if (!barcode) {
                this.notification.add(
                    _t("No se detectó ningún QR o código de barras. Intente nuevamente."),
                    { type: "warning" }
                );
                return;
            }

            this._emitBarcode(barcode);
            this._successFeedback();
        } catch (error) {
            console.error("Error del escáner móvil de inventario", error);

            // Si el bridge nativo estaba disponible y falló, no abrimos
            // automáticamente getUserMedia dentro del WebView: es precisamente
            // el escenario que falla en la app móvil. El lector físico/PDA
            // continúa funcionando por el bus estándar.
            if (this._hasNativeScanner()) {
                this.notification.add(
                    _t(
                        "La app móvil no pudo completar el escaneo nativo. " +
                        "Puede usar el lector integrado del PDA, un lector Bluetooth/USB o intentar nuevamente."
                    ),
                    { type: "danger" }
                );
                return;
            }

            this.notification.add(
                _t(
                    "No fue posible abrir la cámara. Compruebe el permiso de cámara del navegador " +
                    "o utilice un lector PDA/Bluetooth/USB."
                ),
                { type: "danger" }
            );
        }
    }
}

SetuBarcodeHandlerField.template = "setu_inventory_count_management.MobileBarcodeField";

export const setuBarcodeHandlerField = {
    ...charField,
    displayName: _t("Escáner QR / código de barras de inventario"),
    component: SetuBarcodeHandlerField,
    extractProps() {
        return {
            canScanBarcode: true,
        };
    },
    supportedTypes: ["char"],
};

registry.category("fields").add("setu_barcode_handler", setuBarcodeHandlerField);
