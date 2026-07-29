/** @odoo-module **/

import {Component, markup, onWillStart, useState, useSubEnv} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";
import {rpc} from "@web/core/network/rpc";
import {useActionLinks} from "@web/views/view_hook";
import {useService} from "@web/core/utils/hooks";
import {View} from "@web/views/view";

export class DfeDocumentDashboard extends Component {
    static template = "l10n_br_fiscal_dfe.DfeDocumentDashboard";
    static components = {View};
    static props = {"*": true};

    setup() {
        this.actionService = useService("action");
        this.state = useState({bannerHtml: ""});

        // The banner is raw QWeb HTML rendered outside of <View/>, so the
        // generic action-link click handling (<a type="action">) needs to be
        // wired up manually here instead of relying on View's own handling.
        useSubEnv({keepLast: new KeepLast()});
        this.handleActionLinks = useActionLinks({
            resModel: "l10n_br_fiscal_dfe.document",
        });

        onWillStart(async () => {
            const result = await rpc("/l10n_br_fiscal_dfe/document_banner");
            this.state.bannerHtml = markup(result.html);
        });

        this.viewProps = {
            resModel: "l10n_br_fiscal_dfe.document",
            type: "list",
            domain: [["is_own_document", "=", false]],
            selectRecord: (resId) => this.selectRecord(resId),
        };
    }

    selectRecord(resId) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "l10n_br_fiscal_dfe.document",
            views: [[false, "form"]],
            res_id: resId,
        });
    }
}

registry
    .category("actions")
    .add("l10n_br_fiscal_dfe.document_dashboard", DfeDocumentDashboard);
