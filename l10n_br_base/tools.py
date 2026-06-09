# Copyright (C) 2009-Today - Akretion (<http://www.akretion.com>).
# @author Gabriel C. Stabel - Akretion
# @author Renato Lima <renato.lima@akretion.com.br>
# @author Raphael Valyi <raphael.valyi@akretion.com>
# @author Magno Costa <magno.costa@akretion.com.br>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

import requests
from erpbrasil.base.fiscal import cnpj_cpf, ie
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def check_ie(env, l10n_br_ie_code, state, country):
    """
    Checks if 'Inscrição Estadual' field is valid
    using erpbrasil library
    :param env:
    :param l10n_br_ie_code:
    :param state:
    :param country:
    :return:
    """
    if env and l10n_br_ie_code and state and country:
        if country != env.ref("base.br"):
            return  # skip check

        disable_ie_validation = env["ir.config_parameter"].sudo().get_param(
            "l10n_br_base.disable_ie_validation", default=False
        ) or env.context.get("disable_ie_validation")

        if disable_ie_validation:
            return  # skip check

        # TODO: em aberto debate sobre:
        #  Se no caso da empresa ser 'isenta' do IE o campo
        #  deve estar vazio ou pode ter algum valor como abaixo
        if l10n_br_ie_code in ("isento", "isenta", "ISENTO", "ISENTA"):
            return  # skip check

        if not ie.validar(state.code.lower(), l10n_br_ie_code):
            raise ValidationError(
                _(
                    "Estadual Inscription %(inscr)s Invalid for State %(state)s!",
                    inscr=l10n_br_ie_code,
                    state=state.name,
                )
            )


def check_cnpj_cpf(env, cnpj_cpf_value, country):
    """
    Check CNPJ or CPF is valid using erpbrasil library
    :param env:
    :param cnpj_cpf_value:
    :param country:
    :return:
    """
    if env and cnpj_cpf_value and country:
        if country == env.ref("base.br"):
            disable_cpf_cnpj_validation = env["ir.config_parameter"].sudo().get_param(
                "l10n_br_base.disable_cpf_cnpj_validation", default=False
            ) or env.context.get("disable_cpf_cnpj_validation")

            if not disable_cpf_cnpj_validation:
                if not cnpj_cpf.validar(cnpj_cpf_value):
                    # Removendo . / - para diferenciar o CNPJ do CPF
                    # 62.228.384/0001-51 -CNPJ
                    # 62228384000151 - CNPJ
                    # 765.865.078-12 - CPF
                    # 76586507812 - CPF
                    document = "CPF"
                    if (
                        len("".join(char for char in cnpj_cpf_value if char.isdigit()))
                        == 14
                    ):
                        document = "CNPJ"

                    raise ValidationError(
                        _(
                            "%(d_type)s %(d_id)s is invalid!",
                            d_type=document,
                            d_id=cnpj_cpf_value,
                        )
                    )


def requests_with_retries(url, method="GET", retries=3, backoff_factor=0.5, **kwargs):
    """
    Make HTTP requests with automatic retry logic and better error handling.

    Args:
        url (str): The URL to request
        method (str): HTTP method (GET, POST, etc). Default: GET
        retries (int): Number of retries for connection errors. Default: 3
        backoff_factor (float): Backoff factor for retries. Default: 0.5
        **kwargs: Additional arguments to pass to requests

    Returns:
        requests.Response: The response object

    Raises:
        ValidationError: If the request fails after retries or returns error status
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        method_func = getattr(session, method.lower())
        response = method_func(url, **kwargs)

        if response.status_code != 200:
            response_text = (
                response.text.encode()
                if isinstance(response.text, str)
                else response.text
            )
            error_msg = (
                f"Handle other unsuccessful status codes: \n"
                f"URL: {url}\n"
                f"Status Code: {response.status_code}\n"
                f"Reason: {response.reason}\n"
                f"Text: {response_text}"
            )
            raise ValidationError(_(error_msg))

        return response

    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}\nURL: {url}"
        _logger.error(error_msg)
        raise ValidationError(_(error_msg)) from e
