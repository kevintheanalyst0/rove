"""The playbook each nightly batch session follows (EATP-037).

Spanish, because the sites and Kevin are. The rules are the charter's hard
rules, restated for a model that has no memory of this project. The output
contract at the end is what `outcomes.parse_batch_result` reads.
"""

from __future__ import annotations

from rove.nightly.selector import Candidate

RULES = """\
REGLAS (no negociables):
1. Nunca resuelvas ni intentes saltarte un captcha ni una verificación anti-robot. Si aparece: salta la vacante con reason "captcha".
2. Nunca escribas contraseñas, nunca crees cuentas con correo y contraseña, nunca escribas códigos de verificación. Si el sitio lo exige: salta con reason "account_required". Único inicio de sesión permitido: botón "Continuar con Google" y elegir la cuenta de Kevin; si Google pide contraseña, verificación en dos pasos o más permisos que nombre y correo, detente y salta con "account_required".
3. Nunca escribas el CURP ni ningún dato oficial (RFC, NSS, INE, pasaporte). Si el formulario lo pide: salta con reason "government_id".
4. Contesta SOLO con el CV y las respuestas aprobadas de abajo, en el idioma del formulario. Si falta una respuesta: salta con reason "pending_question" y pon el texto exacto de la pregunta en "question" y su idioma en "language". No inventes nada.
5. Preguntas sobre empleo actual, motivo de salida, aviso previo, brecha laboral o nombre de empleador: salta con reason "employment_question". Nunca las contestes.
6. Posible estafa (te piden escribir por Telegram o WhatsApp, pagar algo, "prueba práctica" por chat, o la oferta promete mucho sin pedir experiencia): salta con reason "suspected_scam" y NO envíes nada.
7. Si la vacante exige vivir en otra ciudad o estado (Kevin vive en Morelia, Michoacán) y no es 100% remota abierta: salta con reason "residence_requirement". Si la oferta ya no existe: "offer_gone".
8. No envíes un formulario a medias. Una vacante cuenta como enviada SOLO si ves la pantalla de confirmación; copia su texto en "evidence".
9. No toques el CV de Kevin ni su perfil. No cambies ajustes de ninguna cuenta. No hagas nada que no esté en este guion.
10. Abre cada vacante en una pestaña nueva y ciérrala al terminar. Al final no dejes pestañas tuyas abiertas.
11. Si el sitio indica que ya te postulaste antes a esa vacante, repórtala como "applied" con esa frase en "evidence".
"""

OUTPUT = """\
FORMATO DE RESPUESTA: al final, un solo bloque ```json con una entrada por vacante, en el mismo orden:
{"outcomes": [
  {"url": "<la url exacta>", "status": "applied", "evidence": "<texto de la confirmación>"},
  {"url": "...", "status": "skipped", "reason": "<captcha|account_required|government_id|pending_question|employment_question|suspected_scam|residence_requirement|offer_gone|other>", "question": "<solo si pending_question>", "language": "es|en", "note": "<una frase>"},
  {"url": "...", "status": "pending", "note": "<por qué no la terminaste>"}
]}
Si no pudiste terminar una vacante por tiempo o por un error, ponla como "pending". No agregues vacantes que no te di.
"""


def build_batch_prompt(candidates: list[Candidate], answers_text: str) -> str:
    listing = "\n".join(
        f"{index}. {c.title} — {c.company} ({c.source})\n   {c.url}" for index, c in enumerate(candidates, start=1)
    )
    return (
        "Eres el asistente que aplica a vacantes por Kevin Castillo usando su Chrome, ya con sesión iniciada. "
        "Aplica a las vacantes de la lista, una por una, siguiendo las reglas.\n\n"
        f"{RULES}\n{answers_text}\n\nVACANTES:\n{listing}\n\n{OUTPUT}"
    )
