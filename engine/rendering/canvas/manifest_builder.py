"""IMS CC manifest builder."""

from __future__ import annotations

import datetime
import uuid
from xml.sax.saxutils import escape as xml_escape


def build_manifest_xml(quiz_title: str, guid: str) -> str:
    manifest_id = str(uuid.uuid4())
    meta_res_id = str(uuid.uuid4())
    date_str = datetime.date.today().isoformat()
    folder = guid
    return f"""<?xml version=\"1.0\"?>
<manifest xmlns=\"http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1\" xmlns:lom=\"http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource\" xmlns:imsmd=\"http://www.imsglobal.org/xsd/imsmd_v1p2\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" identifier=\"{manifest_id}\" xsi:schemaLocation=\"http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1 http://www.imsglobal.org/xsd/imscp_v1p1.xsd http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource http://www.imsglobal.org/profile/cc/ccv1p1/LOM/ccv1p1_lomresource_v1p0.xsd http://www.imsglobal.org/xsd/imsmd_v1p2 http://www.imsglobal.org/xsd/imsmd_v1p2p2.xsd\">
	<metadata>
		<schema>IMS Content</schema>
		<schemaversion>1.1.3</schemaversion>
		<imsmd:lom>
			<imsmd:general>
				<imsmd:title>
					<imsmd:string>{xml_escape(quiz_title)}</imsmd:string>
				</imsmd:title>
			</imsmd:general>
			<imsmd:lifeCycle>
				<imsmd:contribute>
					<imsmd:date>
						<imsmd:dateTime>{date_str}</imsmd:dateTime>
					</imsmd:date>
				</imsmd:contribute>
			</imsmd:lifeCycle>
		</imsmd:lom>
	</metadata>
	<organizations/>
	<resources>
		<resource identifier=\"{guid}\" type=\"imsqti_xmlv1p2\">
			<file href=\"{folder}/{guid}.xml\"/>
			<dependency identifierref=\"{meta_res_id}\"/>
		</resource>
		<resource identifier=\"{meta_res_id}\" type=\"associatedcontent/imscc_xmlv1p1/learning-application-resource\" href=\"{folder}/assessment_meta.xml\">
			<file href=\"{folder}/assessment_meta.xml\"/>
		</resource>
	</resources>
</manifest>
"""