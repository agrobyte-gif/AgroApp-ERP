/* El titulo de la pestana en el cliente web lo fija JavaScript, no la
 * plantilla: cuando no hay ninguna parte de titulo activa, Odoo cae a la
 * cadena "Odoo". Aqui se registra una parte permanente con el nombre de la
 * aplicacion, de modo que la pestana siempre diga Agroapp. */

import { registry } from "@web/core/registry";

const marcaService = {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Agroapp" });
    },
};

registry.category("services").add("agroapp_branding", marcaService);
