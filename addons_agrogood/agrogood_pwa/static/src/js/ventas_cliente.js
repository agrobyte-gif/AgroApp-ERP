/* Ventas: dar de alta un cliente desde el telefono.
 *
 * Aparece un restoran nuevo y hasta ahora habia que sentarse en el escritorio
 * para poder venderle. Son seis campos y dos son obligatorios.
 *
 * El RUT se comprueba aqui mismo, mientras el cliente esta delante. Es el
 * unico momento en que se le puede preguntar sin costo: descubrir el digito
 * equivocado la semana que viene significa una llamada mas.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const boton = $("btn-crear");
    if (!boton) { return; }

    async function rpc(ruta, params) {
        const r = await fetch(ruta, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify({jsonrpc: "2.0", method: "call", params: params || {}}),
        });
        const d = await r.json();
        if (d.error) {
            throw new Error((d.error.data && d.error.data.message) || d.error.message);
        }
        return d.result;
    }

    function avisar(texto, esError) {
        const t = $("ag-toast");
        if (!t) { return; }
        t.textContent = texto;
        t.className = "ag-toast ag-show" + (esError ? " ag-error" : "");
        setTimeout(() => { t.className = "ag-toast"; }, 6000);
    }

    // --- el digito verificador, en el telefono --------------------------
    // Se repite aqui el calculo que ya hace el servidor. Duplicarlo se
    // justifica por CUANDO avisa: en el momento de teclearlo, con el cliente
    // al lado. El servidor lo vuelve a comprobar igual, porque una validacion
    // que solo vive en el navegador no valida nada.
    function digito(cuerpo) {
        let suma = 0;
        let mult = 2;
        for (let i = cuerpo.length - 1; i >= 0; i--) {
            suma += parseInt(cuerpo[i], 10) * mult;
            mult = mult === 7 ? 2 : mult + 1;
        }
        const resto = 11 - (suma % 11);
        if (resto === 11) { return "0"; }
        if (resto === 10) { return "K"; }
        return String(resto);
    }

    function rutValido(bruto) {
        const limpio = (bruto || "").toUpperCase().replace(/[^0-9K]/g, "")
            .replace(/^0+/, "");
        if (limpio.length < 8 || limpio.length > 9) { return false; }
        const cuerpo = limpio.slice(0, -1);
        if (!/^\d+$/.test(cuerpo)) { return false; }
        return digito(cuerpo) === limpio.slice(-1);
    }

    const campoRut = $("c-rut");
    campoRut.addEventListener("blur", () => {
        const v = campoRut.value.trim();
        if (!v) {
            campoRut.classList.remove("ag-error");
            return;
        }
        const bien = rutValido(v);
        campoRut.classList.toggle("ag-error", !bien);
        if (!bien) {
            avisar("Ese RUT no cuadra. Preguntaselo ahora, que lo tienes al lado.",
                   true);
        }
    });

    boton.addEventListener("click", async () => {
        if (boton.disabled) { return; }
        const texto = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Un momento...";
        try {
            const r = await rpc("/agrogood/api/ventas/cliente_nuevo", {
                nombre: $("c-nombre").value,
                business_line_id: $("c-linea").value || null,
                vat: $("c-rut").value,
                street: $("c-calle").value,
                city: $("c-ciudad").value,
                mobile: $("c-movil").value,
            });
            if (!r.ok) {
                avisar(r.mensaje, true);
                return;
            }
            let texto_final = r.mensaje;
            if (r.sin_rut) {
                texto_final += " Quedo sin RUT: se le puede vender y repartir,"
                    + " pero no facturar hasta que se complete.";
            }
            $("hecho-texto").textContent = texto_final;
            $("et-form").classList.add("ag-oculto");
            $("et-hecho").classList.remove("ag-oculto");
        } catch (e) {
            avisar(e.message || "No se pudo crear el cliente.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    });
})();
