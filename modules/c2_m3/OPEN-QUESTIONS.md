<!--
 Copyright (c) 2026 Contributors to the Eclipse Foundation

 See the NOTICE file(s) distributed with this work for additional
 information regarding copyright ownership.

 This program and the accompanying materials are made available under the
 terms of the Apache License, Version 2.0 which is available at
 https://www.apache.org/licenses/LICENSE-2.0.

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 License for the specific language governing permissions and limitations
 under the License.

 AI Disclosure: This file was entirely AI-generated.
 The AI-generated portions are made available under CC0-1.0 and not subject
 to the project's license. The human contributor has reviewed and verified
 that the content is correct.

 SPDX-License-Identifier: Apache-2.0 AND CC0-1.0
 Assisted-By: GitHub Copilot (Claude Sonnet 5.5)
-->

# C2-M3 open questions

1. **Company roles of OSP A in `stub-companies.json`.** README 14.3 lists `ONBOARDING_SERVICE_PROVIDER` and `ACTIVE_PARTICIPANT`; FRAMEWORK 7a and `testdata/osp-a-company.json` also list `APP_PROVIDER` and `SERVICE_PROVIDER`. Implemented: the four roles of FRAMEWORK 7a (AGENTS rule 7).
2. **README 7.9, filter `companyId`.** It does not say whether co-viewed accounts match. Implemented: only accounts owned by the company.
3. **README 7.4, `roles` of a subscription account.** 6.5 says the assignable-roles check does not apply to subscription accounts, 7.4 says "check as in 7.2 step 3". Implemented: subscription accounts are only checked for existing roles; own accounts also for assignability.
